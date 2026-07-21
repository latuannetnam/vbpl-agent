from pathlib import Path
from vbpl_kb.config import Settings

def test_settings_uses_prefixed_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VBPL_KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VBPL_KB_ONYX_API_KEY", "test-key")
    settings = Settings()
    assert settings.data_dir == tmp_path
    assert settings.onyx_api_key.get_secret_value() == "test-key"
    assert settings.freshness_hours == 24
