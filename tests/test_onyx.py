import httpx
import pytest
import respx
from vbpl_kb.onyx import OnyxIngestionClient
from vbpl_kb.models import OnyxDocument

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
    route = respx.post(f"{settings.onyx_base_url}/api/ingestion/document").mock(
        return_value=httpx.Response(200, json={"id": "vbpl:123"})
    )
    OnyxIngestionClient(settings).upsert(onyx_document)
    assert b"vbpl:123" in route.calls[0].request.content
    assert b"status_checked_at" in route.calls[0].request.content
