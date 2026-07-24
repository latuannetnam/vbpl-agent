import json
import pytest
import respx
import httpx
from vbpl_kb.config import Settings
from vbpl_kb.connector_control import OnyxConnectorClient, ConnectorControlError


@respx.mock
def test_trigger_posts_run_once() -> None:
    route = respx.post("http://onyx:8080/manage/admin/connector/run-once").mock(
        return_value=httpx.Response(200, json={"success": True, "data": 1})
    )
    client = OnyxConnectorClient(Settings(onyx_base_url="http://onyx:8080", onyx_connector_id=7))
    assert client.trigger(7) == 1
    assert json.loads(route.calls.last.request.content) == {
        "connector_id": 7,
        "credential_ids": None,
        "from_beginning": False
    }


@respx.mock
def test_trigger_raises_on_failure() -> None:
    respx.post("http://onyx:8080/manage/admin/connector/run-once").mock(
        return_value=httpx.Response(500, json={"detail": "Internal server error"})
    )
    client = OnyxConnectorClient(Settings(onyx_base_url="http://onyx:8080", onyx_connector_id=7))
    with pytest.raises(ConnectorControlError):
        client.trigger(7)


@respx.mock
def test_create_connector_posts_creation_request() -> None:
    route = respx.post("http://onyx:8080/manage/admin/connector-with-mock-credential").mock(
        return_value=httpx.Response(200, json={"success": True, "data": 42})
    )
    client = OnyxConnectorClient(Settings(onyx_base_url="http://onyx:8080"))
    cid = client.create_connector("VBPL Export")
    assert cid == 42
    assert json.loads(route.calls.last.request.content) == {
        "name": "VBPL Export",
        "source": "vbpl_export",
        "input_type": "poll",
        "connector_specific_config": {},
        "refresh_freq": 86400,
        "disabled": False,
        "access_type": "public",
    }


@respx.mock
def test_wait_returns_matching_completed_attempt_with_chunk_total() -> None:
    respx.post("http://onyx:8080/manage/admin/connector/indexing-status").mock(
        return_value=httpx.Response(200, json={"statuses": [{
            "connector_id": 7,
            "last_status": "success",
            "in_progress": False,
            "total_chunks": 120,
            "attempt_id": 41,
        }]})
    )
    status = OnyxConnectorClient(
        Settings(onyx_base_url="http://onyx:8080")
    ).wait_for_indexed(7, timeout_seconds=1)
    assert status.attempt_id == 41
    assert status.total_chunks == 120
