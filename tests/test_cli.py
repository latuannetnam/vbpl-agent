import pytest
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
