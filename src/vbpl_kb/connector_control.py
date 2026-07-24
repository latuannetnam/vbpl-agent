import time
from typing import Any
import httpx
from pydantic import BaseModel, ConfigDict
from vbpl_kb.config import Settings


class ConnectorControlError(Exception):
    pass


class ConnectorStatus(BaseModel):
    model_config = ConfigDict(frozen=True)
    connector_id: int
    attempt_id: int | None = None
    last_status: str = "unknown"
    in_progress: bool = False
    total_chunks: int = 0
    raw_status: dict[str, Any] = {}


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

    def get_status(self, connector_id: int) -> ConnectorStatus:
        path = self.settings.onyx_connector_status_path
        try:
            response = self._request("POST", path, json={})
            if response.status_code != 200:
                response = self._request("GET", path)

            if response.status_code == 200:
                data = response.json()
                groups = data if isinstance(data, list) else data.get("statuses", [])
                for group in groups:
                    if isinstance(group, dict):
                        items = group.get("indexing_statuses", [group])
                        for item in items:
                            if isinstance(item, dict):
                                cid = item.get("connector_id")
                                src = item.get("source")
                                if cid == connector_id or src == "vbpl_export":
                                    return ConnectorStatus(
                                        connector_id=connector_id,
                                        attempt_id=item.get("attempt_id"),
                                        last_status=str(item.get("last_status") or item.get("status") or "unknown"),
                                        in_progress=bool(item.get("in_progress", False)),
                                        total_chunks=int(item.get("total_chunks", 0)),
                                        raw_status=item,
                                    )
            return ConnectorStatus(connector_id=connector_id)
        except Exception as e:
            raise ConnectorControlError(f"Failed to get status for connector {connector_id}") from e

    def create_connector(self, name: str = "VBPL Export") -> int:
        try:
            response = self._request("POST", "/manage/admin/connector-with-mock-credential", json={
                "name": name,
                "source": "vbpl_export",
                "input_type": "poll",
                "connector_specific_config": {},
                "refresh_freq": 86400,
                "disabled": False,
                "access_type": "public",
            })
            if response.status_code in (400, 409) and "already exists" in response.text.casefold():
                list_resp = self._request("GET", "/manage/admin/connector")
                if list_resp.status_code == 200:
                    for item in list_resp.json():
                        if isinstance(item, dict) and item.get("name") == name:
                            cid = int(item["id"])
                            cred_ids = item.get("credential_ids", [])
                            if not cred_ids:
                                c_resp = self._request("POST", "/manage/credential", json={
                                    "credential_json": {},
                                    "admin_public": True,
                                    "source": "vbpl_export",
                                })
                                if c_resp.status_code == 200:
                                    cred_id = c_resp.json().get("id")
                                    self._request("PUT", f"/manage/connector/{cid}/credential/{cred_id}", json={
                                        "name": name,
                                        "access_type": "public",
                                    })
                            return cid
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

    def wait_for_indexed(self, connector_id: int, timeout_seconds: float | None = None) -> ConnectorStatus:
        timeout = timeout_seconds if timeout_seconds is not None else self.settings.onyx_connector_timeout_seconds
        start_time = time.monotonic()

        while True:
            if time.monotonic() - start_time > timeout:
                raise ConnectorControlError(f"Timed out waiting for connector {connector_id} to finish indexing")

            try:
                status = self.get_status(connector_id)
                if not status.in_progress and status.last_status in ("success", "completed"):
                    return status
            except Exception:
                pass

            time.sleep(2.0)
