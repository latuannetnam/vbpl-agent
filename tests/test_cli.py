import pytest
from types import SimpleNamespace
from datetime import datetime, UTC, timedelta
from typer.testing import CliRunner
from vbpl_kb.state import StateStore
from vbpl_kb.cli import app

@pytest.fixture
def runner():
    return CliRunner()

@pytest.fixture
def stale_store(tmp_path):
    store = StateStore.open(tmp_path / "state.sqlite3")
    # Add data_dir property dynamically or map it
    store.data_dir = tmp_path
    
    run_id = "run-stale"
    started_at = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    finished_at = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    with store.conn:
        store.conn.execute("""
            INSERT OR REPLACE INTO crawl_runs (run_id, status, coverage, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?)
        """, (run_id, "completed", 1.0, started_at, finished_at))
    store.set_active_run(run_id)
    return store

def test_status_exits_two_when_revision_is_stale(runner, stale_store) -> None:
    result = runner.invoke(app, ["status", "--db-path", str(stale_store.db_path)])
    assert result.exit_code == 2
    # Normalize spaces
    clean_stdout = result.stdout.replace(" ", "").replace("\n", "").replace("\r", "")
    assert '"status":"stale"' in clean_stdout


def test_status_uses_configured_freshness_window(runner, tmp_path, monkeypatch) -> None:
    store = StateStore.open(tmp_path / "state.sqlite3")
    run_id = store.begin_run("run-configured-window")
    with store.conn:
        store.conn.execute(
            "UPDATE crawl_runs SET started_at = ?, finished_at = ? WHERE run_id = ?",
            (
                (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                run_id,
            ),
        )
    store.finish_run(run_id, "completed", 1.0)
    with store.conn:
        store.conn.execute(
            "UPDATE crawl_runs SET finished_at = ? WHERE run_id = ?",
            ((datetime.now(UTC) - timedelta(hours=2)).isoformat(), run_id),
        )
    store.set_active_run(run_id)

    from vbpl_kb.config import Settings
    monkeypatch.setattr("vbpl_kb.cli.Settings", lambda: Settings(freshness_hours=1))
    result = runner.invoke(app, ["status", "--db-path", str(store.db_path)])

    assert result.exit_code == 2
    assert '"status":"stale"' in result.stdout.replace(" ", "").replace("\n", "")


def test_evaluate_refuses_to_guess_onyx_query_route(runner, tmp_path, monkeypatch) -> None:
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text("[]", encoding="utf-8")

    from vbpl_kb.config import Settings
    monkeypatch.setattr("vbpl_kb.cli.Settings", lambda: Settings(onyx_search_path=None))
    result = runner.invoke(app, ["evaluate", str(benchmark)])

    assert result.exit_code == 1
    assert "Onyx search endpoint is not configured" in result.stdout


def test_run_daily_streams_component_progress(runner, tmp_path, monkeypatch) -> None:
    class FakeCrawler:
        def __init__(self, client, store, progress):
            self.progress = progress

        def run(self, revision):
            self.progress("crawl: catalog page 1 discovered; documents=1")
            self.progress("crawl: completed; documents=1/1 (failed=0)")
            return SimpleNamespace(coverage=1.0)

    class FakePublisher:
        def __init__(self, store, onyx, progress):
            self.progress = progress

        def publish(self, revision):
            self.progress("publish: preparing 1 documents")
            self.progress("publish: completed; upserted=1 deleted=0")
            return SimpleNamespace(upserted_count=1, deleted_count=0)

    monkeypatch.setattr("vbpl_kb.cli.Settings", lambda: object())
    monkeypatch.setattr("vbpl_kb.cli.StateStore.open", lambda path: object())
    monkeypatch.setattr("vbpl_kb.cli.VBPLClient", lambda settings: object())
    monkeypatch.setattr("vbpl_kb.cli.OnyxIngestionClient", lambda settings: object())
    monkeypatch.setattr("vbpl_kb.cli.DailyCrawler", FakeCrawler)
    monkeypatch.setattr("vbpl_kb.cli.Publisher", FakePublisher)

    result = runner.invoke(app, ["run-daily", "--db-path", str(tmp_path / "state.sqlite3")])

    assert result.exit_code == 0
    assert "crawl: catalog page 1 discovered; documents=1" in result.output
    assert "publish: completed; upserted=1 deleted=0" in result.output
