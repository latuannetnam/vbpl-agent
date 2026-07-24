import httpx
import json
import pytest
import respx
from vbpl_kb.models import OnyxDocument, OnyxSection
from vbpl_kb.onyx import OnyxIngestionClient
from vbpl_kb.config import Settings

@pytest.fixture
def onyx_document():
    return OnyxDocument(
        document_id="vbpl:123",
        sections=(OnyxSection(section_id="whole", text="Content of document 123.", link="https://vbpl.vn/doc/123"),),
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
    payload = json.loads(route.calls[0].request.content)
    assert payload["document"]["id"] == "vbpl:123"
    assert payload["document"]["sections"] == [
        {"text": "Content of document 123.", "link": "https://vbpl.vn/doc/123"}
    ]
    assert payload["document"]["metadata"]["status_checked_at"] == "2026-07-21T00:00:00+00:00"


def test_upsert_requires_a_confirmed_endpoint_configuration(tmp_path, onyx_document) -> None:
    settings = Settings(
        onyx_ingestion_upsert_path=None,
        onyx_ingestion_delete_path=None,
    )

    with pytest.raises(RuntimeError, match="ingestion endpoint is not configured"):
        OnyxIngestionClient(settings).upsert(onyx_document)


@respx.mock
def test_upsert_retries_a_read_timeout(settings, onyx_document) -> None:
    settings = settings.model_copy(update={"onyx_ingestion_upsert_path": "/onyx-api/ingestion"})
    route = respx.post(f"{settings.onyx_base_url}/onyx-api/ingestion")
    route.side_effect = [
        httpx.ReadTimeout("timed out"),
        httpx.Response(200, json={"document_id": "vbpl:123"}),
    ]

    OnyxIngestionClient(settings).upsert(onyx_document)

    assert route.call_count == 2


def test_onyx_timeout_is_independently_configurable(settings) -> None:
    settings = Settings(
        onyx_request_timeout_seconds=120,
        onyx_ingestion_upsert_path="/onyx-api/ingestion",
    )

    client = OnyxIngestionClient(settings)

    assert client.client.timeout.read == 120
