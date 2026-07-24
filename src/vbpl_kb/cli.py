import json
import hashlib
import typer
from pathlib import Path
from typing import Any
from datetime import datetime, UTC
import httpx
from vbpl_kb.config import Settings
from vbpl_kb.state import StateStore
from vbpl_kb.vbpl_client import VBPLClient
from vbpl_kb.crawl import DailyCrawler
from vbpl_kb.onyx import OnyxIngestionClient
from vbpl_kb.publish import Publisher, PublishBlocked
from vbpl_kb.releases import ReleaseExporter, ReleaseBlocked as ReleaseExportBlocked
from vbpl_kb.connector_control import OnyxConnectorClient, ConnectorControlError

app = typer.Typer()

def get_default_revision() -> str:
    return f"vbpl-{datetime.now(UTC).strftime('%Y-%m-%d')}"

@app.command()
def crawl(
    db_path: str = typer.Option("data/state.sqlite3", "--db-path"),
    revision: str = typer.Option(None, "--revision")
) -> None:
    settings = Settings()
    path = Path(db_path)
    store = StateStore.open(path)
    client = VBPLClient(settings)
    
    rev = revision or get_default_revision()
    crawler = DailyCrawler(client, store, progress=typer.echo)
    typer.echo(f"Starting crawl for revision {rev}...")
    summary = crawler.run(rev)
    typer.echo(f"Crawl finished. Coverage: {summary.coverage:.2f}, Failed IDs: {summary.failed_ids}")



@app.command(name="publish-legacy", help="[Diagnostic-only] Direct ingestion API publisher for legacy testing.")
def publish_legacy(
    db_path: str = typer.Option("data/state.sqlite3", "--db-path"),
    revision: str = typer.Option(..., "--revision")
) -> None:
    settings = Settings()
    path = Path(db_path)
    store = StateStore.open(path)
    onyx = OnyxIngestionClient(settings)
    publisher = Publisher(store, onyx, progress=typer.echo)
    
    try:
        typer.echo(f"Publishing revision {revision} to Onyx (legacy direct mode)...")
        summary = publisher.publish(revision)
        typer.echo(f"Legacy publish complete. Upserted: {summary.upserted_count}, Deleted: {summary.deleted_count}")
    except PublishBlocked as e:
        typer.echo(f"Publish blocked: {e}")
        raise typer.Exit(code=1)


@app.command()
def run_daily(
    db_path: str = typer.Option("data/state.sqlite3", "--db-path"),
    revision: str = typer.Option(None, "--revision")
) -> None:
    settings = Settings()
    path = Path(db_path)
    store = StateStore.open(path)
    client = VBPLClient(settings)
    
    rev = revision or get_default_revision()
    crawler = DailyCrawler(client, store, progress=typer.echo)
    typer.echo(f"Running daily crawl for revision {rev}...")
    crawl_summary = crawler.run(rev)
    typer.echo(f"Crawl finished. Coverage: {crawl_summary.coverage:.2f}")
    
    exporter = ReleaseExporter(store, settings.export_dir)
    try:
        typer.echo(f"Writing release candidate for {rev}...")
        candidate = exporter.write_candidate(rev)
        typer.echo(f"Promoting release {rev}...")
        exporter.promote(candidate)
        typer.echo(f"Export release {rev} promoted successfully.")
    except ReleaseExportBlocked as e:
        typer.echo(f"Daily pipeline blocked on release export step: {e}")
        raise typer.Exit(code=1)

    if settings.onyx_connector_id is not None:
        try:
            connector_client = OnyxConnectorClient(settings)
            typer.echo(f"Triggering Onyx connector ID {settings.onyx_connector_id}...")
            connector_client.trigger(settings.onyx_connector_id)
            typer.echo("Waiting for Onyx connector indexing...")
            connector_client.wait_for_indexed(settings.onyx_connector_id, settings.onyx_connector_timeout_seconds)
            typer.echo("Onyx connector indexing completed.")
        except ConnectorControlError as e:
            typer.echo(f"Daily pipeline blocked on connector step: {e}")
            raise typer.Exit(code=1)

    typer.echo("Daily pipeline completed successfully.")


@app.command()
def status(
    db_path: str = typer.Option("data/state.sqlite3", "--db-path")
) -> None:
    settings = Settings()
    path = Path(db_path)
    if not path.exists():
        typer.echo(json.dumps({"status": "none", "message": "Database file does not exist"}))
        raise typer.Exit(code=2)
        
    store = StateStore.open(path)
    active_run_id = store.get_active_run_id()
    if not active_run_id:
        typer.echo(json.dumps({"status": "none", "message": "No active revision found"}))
        raise typer.Exit(code=2)
        
    run = store.get_run(active_run_id)
    if not run:
        typer.echo(json.dumps({"status": "none", "message": f"Active run {active_run_id} not found in database"}))
        raise typer.Exit(code=2)
        
    if run.status != "completed" or run.coverage != 1.0:
        typer.echo(json.dumps({"status": "partial", "run_id": run.run_id, "message": "Active run is partial or failed"}))
        raise typer.Exit(code=2)
        
    # Check freshness using the same configured window as the daily verifier.
    if run.finished_at:
        age_seconds = (datetime.now(UTC) - run.finished_at).total_seconds()
        if age_seconds > settings.freshness_hours * 3600:
            typer.echo(json.dumps({"status": "stale", "run_id": run.run_id, "finished_at": run.finished_at.isoformat()}))
            raise typer.Exit(code=2)
        else:
            typer.echo(json.dumps({"status": "fresh", "run_id": run.run_id, "finished_at": run.finished_at.isoformat()}))
            raise typer.Exit(code=0)
    else:
        typer.echo(json.dumps({"status": "partial", "run_id": run.run_id, "message": "Active run finished_at is missing"}))
        raise typer.Exit(code=2)


@app.command(name="setup-connector")
def setup_connector(
    name: str = typer.Option("VBPL Export", help="Connector name")
) -> None:
    """Create the VBPL Export connector in Onyx API and output its connector ID."""
    settings = Settings()
    client = OnyxConnectorClient(settings)
    try:
        connector_id = client.create_connector(name=name)
        typer.echo(f"Successfully created connector '{name}' in Onyx (connector_id={connector_id}).")
        typer.echo(f"Set VBPL_KB_ONYX_CONNECTOR_ID={connector_id} in your .env file.")
    except Exception as e:
        typer.echo(f"Failed to create connector: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def evaluate(
    benchmark_path: str = typer.Argument(..., help="Path to benchmark JSON file")
) -> None:
    settings = Settings()
    if not settings.onyx_search_path:
        typer.echo("Evaluation blocked: Onyx search endpoint is not configured")
        raise typer.Exit(code=1)
    path = Path(benchmark_path)
    if not path.exists():
        typer.echo(f"Benchmark file not found: {path}")
        raise typer.Exit(code=1)
        
    with open(path, "r", encoding="utf-8") as f:
        cases = json.load(f)
        
    client = httpx.Client(timeout=settings.request_timeout_seconds)
    
    def search(query_str: str) -> list[dict[str, Any]]:
        url = f"{settings.onyx_base_url.rstrip('/')}{settings.onyx_search_path}"
        headers = {}
        api_key = settings.onyx_api_key.get_secret_value()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        try:
            response = client.post(url, json={"query": query_str}, headers=headers)
            if response.status_code != 200:
                return []
            data = response.json()
            results = []
            raw_results = data.get("results", data.get("documents", data))
            if not isinstance(raw_results, list):
                raw_results = []
                
            for r in raw_results:
                meta = r.get("metadata", {})
                doc_id = r.get("id") or r.get("document_id") or ""
                vbpl_id = doc_id.split(":")[-1] if ":" in doc_id else doc_id
                
                legal_status = meta.get("legal_status", "")
                status_checked_at_str = meta.get("status_checked_at", "")
                
                status_fresh = True
                if status_checked_at_str:
                    try:
                        checked_at = datetime.fromisoformat(status_checked_at_str)
                        age_seconds = (datetime.now(UTC) - checked_at).total_seconds()
                        if age_seconds > settings.freshness_hours * 3600 or legal_status not in ["Còn hiệu lực", "Hết hiệu lực một phần"]:
                            status_fresh = False
                    except Exception:
                        status_fresh = False
                else:
                    status_fresh = False
                    
                provision_key = meta.get("citation_structure", "")
                
                results.append({
                    "vbpl_id": vbpl_id,
                    "provision_key": provision_key,
                    "status_fresh": status_fresh
                })
            return results
        except Exception:
            return []
            
    from vbpl_kb.evaluate import evaluate_retrieval
    report = evaluate_retrieval(cases, search)
    
    typer.echo(f"Evaluation complete. Passed: {report.passed}")
    typer.echo(f"Safety failures: {report.current_law_safety_failures}")
    typer.echo(f"Metrics: {report.metrics}")
    
    if not report.passed:
        raise typer.Exit(code=1)


@app.command(name="onyx-acceptance")
def onyx_acceptance(
    benchmark_path: Path = typer.Argument(..., help="Path to benchmark JSON file"),
    label: str = typer.Option(..., "--label"),
    prompt_path: Path = typer.Option(
        Path("docs/onyx-agent-instruction.md"), "--prompt-path"
    ),
    output_path: Path | None = typer.Option(None, "--output"),
    record_only: bool = typer.Option(False, "--record-only"),
) -> None:
    settings = Settings()
    if not benchmark_path.exists():
        typer.echo(f"Benchmark file not found: {benchmark_path}")
        raise typer.Exit(code=1)

    if (
        settings.onyx_persona_id is None
        or not settings.onyx_model_name
        or settings.onyx_connector_id is None
        or settings.onyx_internal_search_tool_id is None
        or not settings.onyx_document_set_name
    ):
        typer.echo("Onyx acceptance prevalidation failed: Required Settings missing.")
        raise typer.Exit(code=1)

    exporter = ReleaseExporter(StateStore.open(Path("data/state.sqlite3")), settings.export_dir)
    active_release = exporter.read_active()
    if not active_release:
        typer.echo("Onyx acceptance prevalidation failed: Readable active release missing.")
        raise typer.Exit(code=1)
    release_id = active_release.release_id

    prompt_sha256 = ""
    if prompt_path.exists():
        prompt_sha256 = hashlib.sha256(prompt_path.read_bytes()).hexdigest()

    connector_status: dict[str, Any] = {}
    if settings.onyx_connector_id is not None:
        connector_client = OnyxConnectorClient(settings)
        if hasattr(connector_client, "get_status"):
            try:
                status_obj = getattr(connector_client, "get_status")(settings.onyx_connector_id)
                connector_status = status_obj.model_dump()
            except Exception:
                connector_status = {"connector_id": settings.onyx_connector_id}
        else:
            connector_status = {"connector_id": settings.onyx_connector_id}

    with open(benchmark_path, "r", encoding="utf-8") as f:
        cases_data = json.load(f)

    from vbpl_kb.acceptance import AcceptanceCase, AcceptanceContext, run_acceptance
    from vbpl_kb.onyx_chat import OnyxChatClient

    cases = [AcceptanceCase.model_validate(c) for c in cases_data]
    chat_client = OnyxChatClient(settings)

    context = AcceptanceContext(
        label=label,
        model_name=settings.onyx_model_name,
        persona_id=settings.onyx_persona_id,
        prompt_sha256=prompt_sha256,
        release_id=release_id,
        connector_status=connector_status,
    )

    report = run_acceptance(cases, chat_client, context)

    out_file = output_path or (settings.evaluation_dir / f"hierarchy-{label}.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))

    typer.echo(f"Acceptance report written to {out_file}. Passed: {report.passed}")
    if not record_only and not report.passed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
