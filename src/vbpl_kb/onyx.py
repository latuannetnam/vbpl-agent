import httpx
from urllib.parse import quote
from vbpl_kb.config import Settings
from vbpl_kb.models import OnyxDocument

class OnyxIngestionClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.Client(timeout=settings.request_timeout_seconds)

    def close(self) -> None:
        self.client.close()

    def _headers(self) -> dict[str, str]:
        headers = {}
        api_key = self.settings.onyx_api_key.get_secret_value()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

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
        payload = {
            "id": doc.document_id,
            "content": doc.content,
            "link": doc.link,
            "metadata": doc.metadata
        }
        response = self.client.post(url, json=payload, headers=self._headers())
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
        response = self.client.delete(url, headers=self._headers())
        if not 200 <= response.status_code < 300 and response.status_code != 404:
            raise httpx.HTTPStatusError(
                f"Onyx delete failed with status code {response.status_code}",
                request=response.request,
                response=response
            )
