import httpx
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
        url = f"{self.settings.onyx_base_url}/api/ingestion/health"
        try:
            response = self.client.get(url, headers=self._headers())
            return response.status_code == 200
        except Exception:
            return False

    def upsert(self, doc: OnyxDocument) -> None:
        url = f"{self.settings.onyx_base_url}/api/ingestion/document"
        payload = {
            "id": doc.document_id,
            "content": doc.content,
            "link": doc.link,
            "metadata": doc.metadata
        }
        response = self.client.post(url, json=payload, headers=self._headers())
        if response.status_code != 200:
            # Raise non-2xx error without secrets
            raise httpx.HTTPStatusError(
                f"Onyx upsert failed with status code {response.status_code}",
                request=response.request,
                response=response
            )

    def delete(self, document_id: str) -> None:
        url = f"{self.settings.onyx_base_url}/api/ingestion/document/{document_id}"
        response = self.client.delete(url, headers=self._headers())
        if response.status_code not in [200, 204, 404]:
            raise httpx.HTTPStatusError(
                f"Onyx delete failed with status code {response.status_code}",
                request=response.request,
                response=response
            )
