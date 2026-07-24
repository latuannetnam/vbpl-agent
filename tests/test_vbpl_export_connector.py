import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path
import pytest

# Create stub modules for Onyx imports
onyx_interfaces = types.ModuleType("onyx.connectors.interfaces")
class PollConnector:
    def __init__(self, *args: object, **kwargs: object) -> None: pass
class LoadConnector:
    def __init__(self, *args: object, **kwargs: object) -> None: pass
onyx_interfaces.PollConnector = PollConnector  # type: ignore
onyx_interfaces.LoadConnector = LoadConnector  # type: ignore

onyx_models = types.ModuleType("onyx.connectors.models")
class DocumentSource:
    VBPL_EXPORT = "vbpl_export"
class TextSection:
    def __init__(self, text: str, link: str | None = None, heading: str | None = None) -> None:
        self.text = text
        self.link = link
        self.heading = heading
class Document:
    def __init__(
        self,
        id: str,
        sections: list[TextSection],
        source: str,
        metadata: dict,
        semantic_identifier: str,
        title: str | None = None,
        doc_updated_at: str | None = None,
        primary_owners: list | None = None,
        secondary_owners: list | None = None,
        from_ingestion_api: bool = False,
    ) -> None:
        self.id = id
        self.sections = sections
        self.source = source
        self.metadata = metadata
        self.semantic_identifier = semantic_identifier
class Section:
    def __init__(self, link: str | None = None, text: str = "") -> None:
        self.link = link
        self.text = text

onyx_models.DocumentSource = DocumentSource  # type: ignore
onyx_models.TextSection = TextSection  # type: ignore
onyx_models.Document = Document  # type: ignore
onyx_models.Section = Section  # type: ignore

onyx_configs = types.ModuleType("onyx.configs.app_configs")
onyx_configs.INDEXING_MODEL_TITLE_MAX_LEN = 243  # type: ignore
onyx_configs.INDEX_BATCH_SIZE = 10  # type: ignore

sys.modules["onyx.connectors.interfaces"] = onyx_interfaces
sys.modules["onyx.connectors.models"] = onyx_models
sys.modules["onyx.configs.app_configs"] = onyx_configs

connector_path = Path("infra/onyx/overlay/backend/onyx/connectors/vbpl_export/connector.py")
spec = importlib.util.spec_from_file_location("vbpl_export_connector", connector_path)
assert spec and spec.loader
vbpl_connector_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vbpl_connector_module)

VBPLExportConnector = vbpl_connector_module.VBPLExportConnector  # type: ignore
VBPLExportConnectorError = vbpl_connector_module.VBPLExportConnectorError  # type: ignore


@pytest.fixture
def connector_factory(tmp_path: Path):
    def _create(doc_payload: dict):
        export_dir = tmp_path / "exports"
        rel_dir = export_dir / "releases" / "r1"
        rel_dir.mkdir(parents=True, exist_ok=True)
        doc_dir = rel_dir / "documents"
        doc_dir.mkdir(parents=True, exist_ok=True)

        doc_file = doc_dir / "vbpl_1.json"
        doc_bytes = json.dumps(doc_payload, ensure_ascii=False).encode("utf-8")
        doc_sha = hashlib.sha256(doc_bytes).hexdigest()
        doc_file.write_bytes(doc_bytes)

        manifest = {
            "release_id": "r1",
            "projection_schema_version": doc_payload.get("projection_schema_version", 1),
            "document_count": 1,
            "section_count": len(doc_payload.get("sections", [1])),
            "published_at": "2026-07-24T00:00:00Z",
            "documents": [
                {
                    "document_id": doc_payload["document_id"],
                    "relative_path": "documents/vbpl_1.json",
                    "sha256": doc_sha,
                    "updated_at": "2026-07-24T00:00:00Z",
                }
            ],
        }
        manifest_file = rel_dir / "manifest.json"
        manifest_bytes = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        manifest_file.write_bytes(manifest_bytes)
        manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

        active = {
            "release_id": "r1",
            "manifest_path": str(manifest_file.resolve()),
            "manifest_sha256": manifest_sha,
            "published_at": "2026-07-24T00:00:00Z",
        }
        (export_dir / "active-release.json").write_text(json.dumps(active), encoding="utf-8")

        return VBPLExportConnector(str(export_dir))
    return _create


def test_connector_reads_legacy_missing_version_as_one_section(connector_factory) -> None:
    connector = connector_factory({
        "document_id": "vbpl:1",
        "content": "legacy",
        "link": "https://vbpl.vn/1",
        "metadata": {"title": "Legacy"},
    })
    document = list(connector.load_from_state())[0][0]
    assert [section.text for section in document.sections] == ["legacy"]


def test_connector_reads_ordered_schema_v2_sections(connector_factory) -> None:
    connector = connector_factory({
        "projection_schema_version": 2,
        "document_id": "vbpl:1",
        "sections": [
            {"section_id": "dieu-1", "text": "Điều 1", "link": "https://vbpl.vn/1"},
            {"section_id": "dieu-2", "text": "Điều 2", "link": "https://vbpl.vn/1"},
        ],
        "link": "https://vbpl.vn/1",
        "metadata": {"title": "Schema v2"},
    })
    document = list(connector.load_from_state())[0][0]
    assert [section.heading for section in document.sections] == ["dieu-1", "dieu-2"]
    assert all(section.link == "https://vbpl.vn/1" for section in document.sections)


def test_connector_rejects_unsupported_version_before_yield(connector_factory) -> None:
    connector = connector_factory({
        "projection_schema_version": 3,
        "document_id": "vbpl:1",
        "sections": [],
        "metadata": {"title": "Bad"},
    })
    with pytest.raises(VBPLExportConnectorError, match="Unsupported projection schema"):
        list(connector.load_from_state())


def test_connector_sanitizes_oversized_metadata_without_losing_relation_tokens(
    connector_factory,
) -> None:
    connector = connector_factory({
        "projection_schema_version": 2,
        "document_id": "vbpl:1",
        "sections": [{"section_id": "dieu-1", "text": "Điều 1", "link": "https://vbpl.vn/1"}],
        "link": "https://vbpl.vn/1",
        "metadata": {
            "title": "X" * 300,
            "relation_tokens": ["amends:175440"],
        },
    })
    document = list(connector.load_from_state())[0][0]
    assert len(document.metadata["title"]) <= 243
    assert document.metadata["relation_tokens"] == ["amends:175440"]
