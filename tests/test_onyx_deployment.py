from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_local_onyx_directory_is_ignored() -> None:
    assert ".onyx/" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_ui_override_binds_configurable_localhost_port() -> None:
    compose = (ROOT / "infra/onyx/docker-compose.vbpl-ui.yml").read_text(
        encoding="utf-8"
    )

    assert '"127.0.0.1:${ONYX_WEB_UI_PORT:-3001}:80"' in compose
    assert r"tr -d '\\015'" in compose


def test_start_script_uses_scoped_legacy_shutdown_and_project_name() -> None:
    script = (ROOT / "scripts/start-onyx.ps1").read_text(encoding="utf-8")

    assert "--project-name onyx down" in script
    assert "--project-name onyx --profile s3-filestore down" in script
    assert "--project-name vbpl-onyx" in script
    assert "--profile s3-filestore up -d" in script
    assert "bootstrap-onyx.ps1" in script
    assert "Repair-DetachedMinioContainer" in script
    assert "docker rm -f $containerId" in script
    assert "Remove-Volume" not in script
    assert "docker volume rm" not in script


def test_pipeline_uses_the_project_owned_onyx_network() -> None:
    compose = (ROOT / "docker-compose.vbpl.yml").read_text(encoding="utf-8")

    assert "http://api_server:8080" in compose
    assert "name: vbpl-onyx_default" in compose
    assert "external: true" in compose


def test_environment_example_exposes_ui_port_and_verified_routes() -> None:
    environment = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "ONYX_WEB_UI_PORT=3001" in environment
    assert "VBPL_KB_ONYX_CONNECTOR_ID=" in environment
    assert "VBPL_KB_ONYX_SEARCH_PATH=/admin/search" in environment


def test_schema_v2_verification_script_exists() -> None:
    script_path = ROOT / "scripts/verify-schema-v2-index.py"
    assert script_path.exists()
    content = script_path.read_text(encoding="utf-8")
    assert "REQUIRED_FIELDS" in content
    assert "corpus_view" in content
    assert "statutory_group" in content
