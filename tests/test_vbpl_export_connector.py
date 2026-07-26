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
class SlimConnector:
    def __init__(self, *args: object, **kwargs: object) -> None: pass
onyx_interfaces.PollConnector = PollConnector  # type: ignore
onyx_interfaces.LoadConnector = LoadConnector  # type: ignore
onyx_interfaces.SlimConnector = SlimConnector  # type: ignore

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
class SlimDocument:
    def __init__(self, id: str) -> None:
        self.id = id

onyx_models.DocumentSource = DocumentSource  # type: ignore
onyx_models.TextSection = TextSection  # type: ignore
onyx_models.Document = Document  # type: ignore
onyx_models.SlimDocument = SlimDocument  # type: ignore

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
def create_fixture_release(tmp_path: Path):
    export_dir = tmp_path / "exports"
    rel_dir = export_dir / "releases" / "r1"
    rel_dir.mkdir(parents=True, exist_ok=True)

    # Current view
    cur_dir = rel_dir / "current"
    cur_dir.mkdir(parents=True, exist_ok=True)
    cur_doc = {"projection_schema_version": 2, "document_id": "vbpl:101:current:article:dieu-01", "sections": [{"section_id": "dieu-01", "text": "Current text", "link": "http://x"}], "metadata": {"title": "Doc 101"}}
    (cur_dir / "documents-00000.jsonl").write_text(json.dumps(cur_doc) + "\n", encoding="utf-8")
    (cur_dir / "active-ids.jsonl").write_text("vbpl:101:current:article:dieu-01\n", encoding="utf-8")
    (cur_dir / "delta-00000.jsonl").write_text(json.dumps(cur_doc) + "\n", encoding="utf-8")

    # History view
    hist_dir = rel_dir / "history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    hist_doc = {"projection_schema_version": 2, "document_id": "vbpl:101:history:ver1:article:dieu-01", "sections": [{"section_id": "dieu-01", "text": "History text", "link": "http://x"}], "metadata": {"title": "Doc 101 H"}}
    (hist_dir / "documents-00000.jsonl").write_text(json.dumps(hist_doc) + "\n", encoding="utf-8")
    (hist_dir / "active-ids.jsonl").write_text("vbpl:101:history:ver1:article:dieu-01\n", encoding="utf-8")
    (hist_dir / "delta-00000.jsonl").write_text(json.dumps(hist_doc) + "\n", encoding="utf-8")

    # Evidence view
    ev_dir = rel_dir / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    ev_doc = {"projection_schema_version": 2, "document_id": "vbpl:101:evidence:detail:ev123", "sections": [{"section_id": "ev123", "text": "Evidence proof", "link": "http://x"}], "metadata": {"title": "Doc 101 EV"}}
    (ev_dir / "documents-00000.jsonl").write_text(json.dumps(ev_doc) + "\n", encoding="utf-8")
    (ev_dir / "active-ids.jsonl").write_text("vbpl:101:evidence:detail:ev123\n", encoding="utf-8")
    (ev_dir / "delta-00000.jsonl").write_text(json.dumps(ev_doc) + "\n", encoding="utf-8")

    manifest = {"release_id": "r1", "views": {"current": {}, "history": {}, "evidence": {}}}
    manifest_file = rel_dir / "manifest.json"
    manifest_bytes = json.dumps(manifest).encode("utf-8")
    manifest_file.write_bytes(manifest_bytes)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

    active = {
        "release_id": "r1",
        "manifest_path": str(manifest_file.resolve()),
        "manifest_sha256": manifest_sha,
        "published_at": "2026-07-26T12:00:00Z",
    }
    (export_dir / "active-release.json").write_text(json.dumps(active), encoding="utf-8")
    return export_dir


def test_connector_view_isolation(create_fixture_release) -> None:
    export_dir = create_fixture_release

    connector_cur = VBPLExportConnector("current", str(export_dir))
    docs_cur = list(connector_cur.load_from_state())[0]
    assert len(docs_cur) == 1
    assert docs_cur[0].id == "vbpl:101:current:article:dieu-01"

    connector_hist = VBPLExportConnector("history", str(export_dir))
    docs_hist = list(connector_hist.load_from_state())[0]
    assert len(docs_hist) == 1
    assert docs_hist[0].id == "vbpl:101:history:ver1:article:dieu-01"

    connector_ev = VBPLExportConnector("evidence", str(export_dir))
    docs_ev = list(connector_ev.load_from_state())[0]
    assert len(docs_ev) == 1
    assert docs_ev[0].id == "vbpl:101:evidence:detail:ev123"


def test_connector_refuses_invalid_view(create_fixture_release) -> None:
    export_dir = create_fixture_release
    with pytest.raises(VBPLExportConnectorError, match="Invalid corpus_view"):
        VBPLExportConnector("invalid_view", str(export_dir))


def test_connector_slim_documents_view_scoped(create_fixture_release) -> None:
    export_dir = create_fixture_release
    connector_cur = VBPLExportConnector("current", str(export_dir))
    slims = list(connector_cur.retrieve_all_slim_documents())[0]
    assert len(slims) == 1
    assert slims[0].id == "vbpl:101:current:article:dieu-01"
