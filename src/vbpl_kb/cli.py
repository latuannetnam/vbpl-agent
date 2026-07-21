import json
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
    crawler = DailyCrawler(client, store)
    typer.echo(f"Starting crawl for revision {rev}...")
    summary = crawler.run(rev)
    typer.echo(f"Crawl finished. Coverage: {summary.coverage:.2f}, Failed IDs: {summary.failed_ids}")

@app.command()
def publish(
    db_path: str = typer.Option("data/state.sqlite3", "--db-path"),
    revision: str = typer.Option(..., "--revision")
) -> None:
    settings = Settings()
    path = Path(db_path)
    store = StateStore.open(path)
    onyx = OnyxIngestionClient(settings)
    publisher = Publisher(store, onyx)
    
    try:
        typer.echo(f"Publishing revision {revision} to Onyx...")
        summary = publisher.publish(revision)
        typer.echo(f"Publish complete. Upserted: {summary.upserted_count}, Deleted: {summary.deleted_count}")
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
    onyx = OnyxIngestionClient(settings)
    
    rev = revision or get_default_revision()
    crawler = DailyCrawler(client, store)
    typer.echo(f"Running daily crawl for revision {rev}...")
    crawl_summary = crawler.run(rev)
    typer.echo(f"Crawl finished. Coverage: {crawl_summary.coverage:.2f}")
    
    publisher = Publisher(store, onyx)
    try:
        typer.echo(f"Running daily publish for revision {rev}...")
        pub_summary = publisher.publish(rev)
        typer.echo(f"Daily pipeline completed. Upserted: {pub_summary.upserted_count}, Deleted: {pub_summary.deleted_count}")
    except PublishBlocked as e:
        typer.echo(f"Daily pipeline blocked on publish step: {e}")
        raise typer.Exit(code=1)

@app.command()
def status(
    db_path: str = typer.Option("data/state.sqlite3", "--db-path")
) -> None:
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
        
    # Check freshness (within 24 hours)
    if run.finished_at:
        age_seconds = (datetime.now(UTC) - run.finished_at).total_seconds()
        if age_seconds > 86400:
            typer.echo(json.dumps({"status": "stale", "run_id": run.run_id, "finished_at": run.finished_at.isoformat()}))
            raise typer.Exit(code=2)
        else:
            typer.echo(json.dumps({"status": "fresh", "run_id": run.run_id, "finished_at": run.finished_at.isoformat()}))
            raise typer.Exit(code=0)
    else:
        typer.echo(json.dumps({"status": "partial", "run_id": run.run_id, "message": "Active run finished_at is missing"}))
        raise typer.Exit(code=2)

@app.command()
def evaluate(
    benchmark_path: str = typer.Argument(..., help="Path to benchmark JSON file")
) -> None:
    settings = Settings()
    path = Path(benchmark_path)
    if not path.exists():
        typer.echo(f"Benchmark file not found: {path}")
        raise typer.Exit(code=1)
        
    with open(path, "r", encoding="utf-8") as f:
        cases = json.load(f)
        
    client = httpx.Client(timeout=settings.request_timeout_seconds)
    
    def search(query_str: str) -> list[dict[str, Any]]:
        url = f"{settings.onyx_base_url}/api/query"
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
                        if age_seconds > 86400 or legal_status not in ["Còn hiệu lực", "Hết hiệu lực một phần"]:
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

if __name__ == "__main__":
    app()
