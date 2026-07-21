import time
from typing import Any
import httpx
from vbpl_kb.config import Settings

class VBPLSchemaError(Exception):
    pass

class VBPLDetail:
    def __init__(self, vbpl_id: str, title: str, eff_status: str, eff_from: str | None, raw_json: str, raw_data: dict[str, Any]):
        self.vbpl_id = vbpl_id
        self.title = title
        self.eff_status = eff_status
        self.eff_from = eff_from
        self.raw_json = raw_json
        self.raw_data = raw_data

class VBPLClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.Client(timeout=settings.request_timeout_seconds)

    def close(self) -> None:
        self.client.close()

    def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        retries = 3
        delay = 0.1
        for attempt in range(retries):
            try:
                response = self.client.request(method, url, **kwargs)
                if response.status_code in [429, 500, 502, 503, 504]:
                    response.raise_for_status()
                else:
                    response.raise_for_status()
                    return response
            except httpx.HTTPError as e:
                is_retryable = False
                if isinstance(e, httpx.HTTPStatusError):
                    if e.response.status_code in [429, 500, 502, 503, 504]:
                        is_retryable = True
                
                if is_retryable and attempt < retries - 1:
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise e
        raise httpx.HTTPError("Max retries exceeded")

    def list_catalog_page(self, page_number: int, page_size: int) -> list[dict[str, Any]]:
        url = f"{self.settings.vbpl_gateway_url}/doc/all"
        payload = {
            "pageNumber": page_number,
            "pageSize": page_size,
            "sortDirection": "desc",
            "sortBy": "viewCount",
            "sortByViewCount": True,
        }
        response = self._request_with_retry("POST", url, json=payload)
        try:
            data = response.json()
        except ValueError as e:
            raise VBPLSchemaError("Response is not valid JSON") from e

        if not isinstance(data, dict) or "data" not in data:
            raise VBPLSchemaError("Missing 'data' field in response")
        
        docs = data["data"]
        if isinstance(docs, dict) and "items" in docs:
            docs = docs["items"]
        if not isinstance(docs, list):
            raise VBPLSchemaError("'data' field is not a list")
            
        return docs

    def get_detail(self, vbpl_id: str) -> VBPLDetail:
        url = f"{self.settings.vbpl_gateway_url}/doc/{vbpl_id}"
        response = self._request_with_retry("GET", url)
        try:
            data = response.json()
        except ValueError as e:
            raise VBPLSchemaError("Response is not valid JSON") from e

        if not isinstance(data, dict) or "data" not in data:
            raise VBPLSchemaError("Missing 'data' field in response")
        
        doc_data = data["data"]
        if not isinstance(doc_data, dict):
            raise VBPLSchemaError("'data' field is not a dict")
        
        if "id" not in doc_data or doc_data["id"] is None:
            raise VBPLSchemaError("Missing required field 'data.id'")
        eff_from = doc_data.get("effFrom")
        title = doc_data.get("title")
        eff_status = doc_data.get("effStatus")
        return VBPLDetail(
            vbpl_id=str(doc_data["id"]),
            title=title if isinstance(title, str) else "",
            eff_status=eff_status.get("name", "") if isinstance(eff_status, dict) else "",
            eff_from=str(eff_from) if eff_from is not None else None,
            raw_json=response.text,
            raw_data=doc_data
        )

    def get_canonical_page(self, vbpl_id: str) -> str:
        response = self._request_with_retry(
            "GET", f"https://vbpl.vn/van-ban/chi-tiet/--{vbpl_id}"
        )
        return response.text
