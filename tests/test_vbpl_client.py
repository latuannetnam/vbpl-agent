import httpx
import pytest
import respx
import json
from vbpl_kb.vbpl_client import VBPLClient, VBPLSchemaError

@respx.mock
def test_detail_extracts_status(settings, load_fixture) -> None:
    respx.get(f"{settings.vbpl_gateway_url}/doc/123").mock(
        return_value=httpx.Response(200, json=load_fixture("detail-current.json"))
    )
    assert VBPLClient(settings).get_detail("123").eff_status == "Còn hiệu lực"

@respx.mock
def test_detail_rejects_missing_status(settings) -> None:
    respx.get(f"{settings.vbpl_gateway_url}/doc/123").mock(
        return_value=httpx.Response(200, json={"data": {"id": 123, "title": "X"}})
    )
    with pytest.raises(VBPLSchemaError, match="effStatus.name"):
        VBPLClient(settings).get_detail("123")

@respx.mock
def test_client_retries_on_503(settings) -> None:
    client = VBPLClient(settings)
    route = respx.get(f"{settings.vbpl_gateway_url}/doc/123")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(200, json={
            "data": {
                "id": 123,
                "title": "X",
                "effStatus": {"name": "Còn hiệu lực"},
                "effFrom": "2024-01-01"
            }
        })
    ]
    detail = client.get_detail("123")
    assert detail.eff_status == "Còn hiệu lực"
    assert route.call_count == 2

@respx.mock
def test_client_does_not_retry_on_404(settings) -> None:
    client = VBPLClient(settings)
    route = respx.get(f"{settings.vbpl_gateway_url}/doc/123").mock(
        return_value=httpx.Response(404)
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.get_detail("123")
    assert route.call_count == 1

@respx.mock
def test_list_catalog_page(settings, load_fixture) -> None:
    client = VBPLClient(settings)
    route = respx.post(f"{settings.vbpl_gateway_url}/doc/all").mock(
        return_value=httpx.Response(200, json=load_fixture("catalog-page.json"))
    )
    docs = client.list_catalog_page(page_number=1, page_size=20)
    assert len(docs) == 2
    assert docs[0]["id"] == 123
    assert route.call_count == 1
    assert json.loads(route.calls[0].request.content) == {"page": 1, "size": 20}
