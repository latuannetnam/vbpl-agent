import time
from typing import Any
import httpx
from vbpl_kb.config import Settings


class ConnectorControlError(Exception):
    pass


class OnyxConnectorClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        api_key = self.settings.onyx_api_key.get_secret_value()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> httpx.Response:
        url = f"{self.settings.onyx_base_url.rstrip('/')}{path}"
        with httpx.Client(timeout=self.settings.onyx_request_timeout_seconds) as client:
            return client.request(method, url, json=json, headers=self._headers())

    def trigger(self, connector_id: int, from_beginning: bool = False) -> int:
        path = self.settings.onyx_connector_run_once_path
        try:
            response = self._request("POST", path, json={
                "connector_id": connector_id,
                "credential_ids": None,
                "from_beginning": from_beginning,
            })
            response.raise_for_status()
            payload = response.json()
            if payload.get("success") is not True or not isinstance(payload.get("data"), int):
                raise ConnectorControlError("Onyx did not accept the connector trigger")
            return payload["data"]
        except Exception as e:
            if isinstance(e, ConnectorControlError):
                raise
            raise ConnectorControlError(f"Failed to trigger connector {connector_id}") from e

    def create_connector(self, name: str = "VBPL Export") -> int:
        try:
            response = self._request("POST", "/manage/admin/connector-with-mock-credential", json={
                "name": name,
                "source": "vbpl_export",
                "input_type": "poll",
                "connector_specific_config": {},
                "refresh_freq": 86400,
                "disabled": False,
            })
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data")
            if isinstance(data, int):
                return data
            if isinstance(data, dict) and "connector_id" in data:
                return data["connector_id"]
            if payload.get("success") and isinstance(payload.get("data"), int):
                return payload["data"]
            raise ConnectorControlError("Failed to parse created connector ID from Onyx response")
        except Exception as e:
            if isinstance(e, ConnectorControlError):
                raise
            raise ConnectorControlError("Failed to create connector in Onyx") from e

    def wait_for_indexed(self, connector_id: int, timeout_seconds: float | None = None) -> None:
        timeout = timeout_seconds if timeout_seconds is not None else self.settings.onyx_connector_timeout_seconds
        start_time = time.monotonic()
        path = self.settings.onyx_connector_status_path

        while True:
            if time.monotonic() - start_time > timeout:
                raise ConnectorControlError(f"Timed out waiting for connector {connector_id} to finish indexing")

            try:
                response = self._request("GET", path)
                if response.status_code == 200:
                    data = response.json()
                    # If Onyx returns a list of status objects or a dict
                    statuses = data if isinstance(data, list) else data.get("statuses", [])
                    in_progress = False
                    for item in statuses:
                        if isinstance(item, dict) and item.get("connector_id") == connector_id:
                            status_str = str(item.get("status", "")).casefold()
                            if status_str in ("in_progress", "running", "indexing"):
                                in_progress = True
                                break
                            if status_str in ("failed", "error"):
                                raise ConnectorControlError(f"Connector {connector_id} indexing failed: {item}")
                    if not in_progress:
                        return
            except Exception as e:
                if isinstance(e, ConnectorControlError):
                    raise
                # transient error, retry after sleep
                pass

            time.sleep(2.0)
