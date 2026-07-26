from pathlib import Path

def test_compose_uses_persistent_internal_volume() -> None:
    path = Path("docker-compose.vbpl.yml")
    assert path.exists(), "docker-compose.vbpl.yml does not exist"
    text = path.read_text(encoding="utf-8")
    assert "vbpl-pipeline-data:/app/data" in text
    assert 'restart: "no"' in text
    assert 'command: ["run-daily"]' in text
    assert "VBPL_KB_ONYX_REQUEST_TIMEOUT_SECONDS=${VBPL_KB_ONYX_REQUEST_TIMEOUT_SECONDS:-120}" in text
