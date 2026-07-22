import json
from pathlib import Path


def test_connector_patch_registers_ce_source_without_pruning() -> None:
    patch = Path("infra/onyx/patches/vbpl-export-connector.patch").read_text(encoding="utf-8")
    assert 'VBPL_EXPORT = "vbpl_export"' in patch
    assert "VBPLExportConnector" in patch
    assert "SlimConnector" not in patch


def test_lock_file_specifies_pinned_onyx_ce_revision() -> None:
    lock_path = Path("infra/onyx/onyx.lock.json")
    assert lock_path.exists()
    lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
    assert "repository" in lock_data
    assert "revision" in lock_data
    assert len(lock_data["revision"]) == 40


def test_overlay_connector_implements_vbpl_export() -> None:
    connector_file = Path("infra/onyx/overlay/backend/onyx/connectors/vbpl_export/connector.py")
    assert connector_file.exists()
    content = connector_file.read_text(encoding="utf-8")
    assert "class VBPLExportConnector" in content
    assert "active-release.json" in content


def test_connector_mount_is_read_only_and_background_only() -> None:
    compose = Path("infra/onyx/docker-compose.vbpl-connector.yml").read_text(encoding="utf-8")
    assert "background:" in compose
    assert "VBPL_EXPORT_HOST_PATH:/app/vbpl-export:ro" in compose
    assert "api_server:" in compose

