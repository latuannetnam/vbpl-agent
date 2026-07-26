from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_bootstrap_script_configures_three_multi_resolution_connectors() -> None:
    script_path = ROOT / "scripts" / "bootstrap-onyx.ps1"
    assert script_path.exists()

    content = script_path.read_text(encoding="utf-8")
    assert "vbpl_current" in content
    assert "vbpl_history" in content
    assert "vbpl_evidence" in content

    assert "VBPL Current" in content
    assert "VBPL History" in content
    assert "VBPL Evidence" in content

    assert "corpus_view" in content
