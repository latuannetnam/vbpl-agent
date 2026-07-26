from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VBPL_KB_", env_file=".env", extra="ignore")

    database_url: SecretStr = SecretStr("")
    pipeline_lock_key: int = 868075126
    data_dir: Path = Path("data")
    evidence_dir: Path = Path("/app/data/evidence")
    export_dir: Path = Path("/app/data/exports")

    vbpl_gateway_url: str = "https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public"
    onyx_base_url: str = "http://localhost:8080"
    onyx_api_key: SecretStr = SecretStr("")
    onyx_ingestion_upsert_path: str | None = None
    onyx_ingestion_delete_path: str | None = None
    onyx_ingestion_cc_pair_id: int | None = None
    onyx_search_path: str | None = None
    onyx_health_path: str | None = None
    onyx_connector_id: int | None = None
    onyx_connector_run_once_path: str = "/manage/admin/connector/run-once"
    onyx_connector_status_path: str = "/manage/admin/connector/indexing-status"
    onyx_connector_timeout_seconds: float = 7200.0
    onyx_chat_path: str = "/chat/send-chat-message"
    onyx_persona_id: int | None = None
    onyx_model_name: str = ""
    onyx_internal_search_tool_id: int | None = None
    onyx_document_set_name: str = ""
    evaluation_dir: Path = Path("data/evaluations")
    freshness_hours: int = 24
    request_timeout_seconds: float = 30.0
    onyx_request_timeout_seconds: float = 120.0
    max_pages: int | None = None
