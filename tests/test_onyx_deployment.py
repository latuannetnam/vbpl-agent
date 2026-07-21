from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_local_onyx_directory_is_ignored() -> None:
    assert ".onyx/" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_ui_override_binds_configurable_localhost_port() -> None:
    compose = (ROOT / "infra/onyx/docker-compose.vbpl-ui.yml").read_text(
        encoding="utf-8"
    )

    assert '"127.0.0.1:${ONYX_WEB_UI_PORT:-3001}:80"' in compose
    assert "tr -d '\\015'" in compose
