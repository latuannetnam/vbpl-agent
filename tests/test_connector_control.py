import json
import pytest
import respx
import httpx
from vbpl_kb.config import Settings
from vbpl_kb.connector_control import OnyxConnectorClient, ConnectorControlError


@respx.mock
def test_trigger_posts_run_once() -> None:
    route = respx.post("http://onyx:8080/admin/connector/run-once").mock(
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
    respx.post("http://onyx:8080/admin/connector/run-once").mock(
        return_value=httpx.Response(500, json={"detail": "Internal server error"})
    )
    client = OnyxConnectorClient(Settings(onyx_base_url="http://onyx:8080", onyx_connector_id=7))
    with pytest.raises(ConnectorControlError):
        client.trigger(7)
