import httpx
import time
from typing import Any
from urllib.parse import quote
from vbpl_kb.config import Settings
from vbpl_kb.models import OnyxDocument

class OnyxIngestionClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.Client(timeout=settings.onyx_request_timeout_seconds)

    def close(self) -> None:
        self.client.close()

    def _headers(self) -> dict[str, str]:
        headers = {}
        api_key = self.settings.onyx_api_key.get_secret_value()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        retries = 3
        delay = 0.5
        for attempt in range(retries):
            try:
                response = self.client.request(method, url, **kwargs)
            except httpx.TimeoutException:
                if attempt == retries - 1:
                    raise
            else:
                if response.status_code not in [429, 500, 502, 503, 504] or attempt == retries - 1:
                    return response
            time.sleep(delay)
            delay *= 2
        raise RuntimeError("Onyx request retry loop exhausted")

    def healthcheck(self) -> bool:
        if not self.settings.onyx_health_path:
            return False
        url = f"{self.settings.onyx_base_url.rstrip('/')}{self.settings.onyx_health_path}"
        try:
            response = self.client.get(url, headers=self._headers())
            return response.status_code == 200
        except Exception:
            return False

    def upsert(self, doc: OnyxDocument) -> None:
        if not self.settings.onyx_ingestion_upsert_path:
            raise RuntimeError("Onyx ingestion endpoint is not configured")
        url = f"{self.settings.onyx_base_url.rstrip('/')}{self.settings.onyx_ingestion_upsert_path}"
        semantic_identifier = doc.metadata.get("document_number") or doc.document_id
        payload: dict[str, object] = {
            "document": {
                "id": doc.document_id,
                "semantic_identifier": semantic_identifier,
                "title": doc.metadata.get("title", semantic_identifier),
                "sections": [{"text": doc.content, "link": doc.link}],
                "source": "file",
                "metadata": doc.metadata,
            }
        }
        if self.settings.onyx_ingestion_cc_pair_id is not None:
            payload["cc_pair_id"] = self.settings.onyx_ingestion_cc_pair_id
        response = self._request_with_retry("POST", url, json=payload, headers=self._headers())
        if not 200 <= response.status_code < 300:
            # Raise non-2xx error without secrets
            raise httpx.HTTPStatusError(
                f"Onyx upsert failed with status code {response.status_code}",
                request=response.request,
                response=response
            )

    def delete(self, document_id: str) -> None:
        if not self.settings.onyx_ingestion_delete_path:
            raise RuntimeError("Onyx ingestion endpoint is not configured")
        path = self.settings.onyx_ingestion_delete_path.format(document_id=quote(document_id, safe=""))
        url = f"{self.settings.onyx_base_url.rstrip('/')}{path}"
        response = self._request_with_retry("DELETE", url, headers=self._headers())
        if not 200 <= response.status_code < 300 and response.status_code != 404:
            raise httpx.HTTPStatusError(
                f"Onyx delete failed with status code {response.status_code}",
                request=response.request,
                response=response
            )
