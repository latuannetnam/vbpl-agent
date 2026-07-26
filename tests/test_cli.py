from typing import Any
from types import SimpleNamespace
import pytest
from typer.testing import CliRunner

from vbpl_kb.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_evaluate_refuses_to_guess_onyx_query_route(runner: CliRunner, tmp_path: Any, monkeypatch: Any) -> None:
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text("[]", encoding="utf-8")

    from vbpl_kb.config import Settings
    monkeypatch.setattr("vbpl_kb.cli.Settings", lambda: Settings(onyx_search_path=None))
    result = runner.invoke(app, ["evaluate", str(benchmark)])

    assert result.exit_code == 1
    assert "Onyx search endpoint is not configured" in result.stdout


def test_run_daily_streams_component_progress(runner: CliRunner, tmp_path: Any, monkeypatch: Any) -> None:
    class FakeCrawler:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.progress = kwargs.get("progress") or (args[2] if len(args) > 2 else None)

        def run(self, revision: str) -> SimpleNamespace:
            if callable(self.progress):
                self.progress("crawl: catalog page 1 discovered; documents=1")
                self.progress("crawl: completed; documents=1/1 (failed=0)")
            return SimpleNamespace(coverage=1.0, catalog_complete=True, failed_ids=[])

    class FakeReleaseExporter:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def write_candidate(self, revision: str) -> SimpleNamespace:
            return SimpleNamespace(release_id=revision)

        def promote(self, candidate: SimpleNamespace) -> SimpleNamespace:
            return SimpleNamespace(release_id=candidate.release_id)

    class FakeSettings:
        export_dir = tmp_path / "exports"
        onyx_connector_id = None

    class FakeStore:
        def pending_delta_batches(self) -> list[Any]:
            return []

    monkeypatch.setattr("vbpl_kb.cli.Settings", lambda: FakeSettings())
    monkeypatch.setattr("vbpl_kb.cli.StateStore.open", lambda path: FakeStore())
    monkeypatch.setattr("vbpl_kb.cli.VBPLClient", lambda settings: object())
    monkeypatch.setattr("vbpl_kb.cli.DailyCrawler", FakeCrawler)
    monkeypatch.setattr("vbpl_kb.cli.ReleaseExporter", FakeReleaseExporter)

    result = runner.invoke(app, ["run-daily", "--db-path", str(tmp_path / "state.sqlite3")])

    assert result.exit_code == 0
    assert "crawl: catalog page 1 discovered; documents=1" in result.output
    assert "Export release" in result.output
