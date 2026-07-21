import httpx
import pytest
import respx
from vbpl_kb.onyx import OnyxIngestionClient
from vbpl_kb.models import OnyxDocument
from vbpl_kb.config import Settings

@pytest.fixture
def onyx_document():
    return OnyxDocument(
        document_id="vbpl:123",
        content="Content of document 123.",
        link="https://vbpl.vn/doc/123",
        metadata={"status_checked_at": "2026-07-21T00:00:00+00:00"}
    )

@respx.mock
def test_upsert_sends_stable_id_and_provenance(settings, onyx_document) -> None:
    settings = settings.model_copy(update={"onyx_ingestion_upsert_path": "/api/ingestion/document"})
    route = respx.post(f"{settings.onyx_base_url}/api/ingestion/document").mock(
        return_value=httpx.Response(200, json={"id": "vbpl:123"})
    )
    OnyxIngestionClient(settings).upsert(onyx_document)
    assert b"vbpl:123" in route.calls[0].request.content
    assert b"status_checked_at" in route.calls[0].request.content


def test_upsert_requires_a_confirmed_endpoint_configuration(tmp_path, onyx_document) -> None:
    settings = Settings(
        onyx_ingestion_upsert_path=None,
        onyx_ingestion_delete_path=None,
    )

    with pytest.raises(RuntimeError, match="ingestion endpoint is not configured"):
        OnyxIngestionClient(settings).upsert(onyx_document)
