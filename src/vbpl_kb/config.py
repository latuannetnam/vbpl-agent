from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VBPL_KB_", env_file=".env", extra="ignore")
    vbpl_gateway_url: str = "https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public"
    onyx_base_url: str = "http://localhost:8080"
    onyx_api_key: SecretStr = SecretStr("")
    onyx_ingestion_upsert_path: str | None = None
    onyx_ingestion_delete_path: str | None = None
    onyx_ingestion_cc_pair_id: int | None = None
    onyx_search_path: str | None = None
    onyx_health_path: str | None = None
    data_dir: Path = Path("data")
    freshness_hours: int = 24
    request_timeout_seconds: float = 30.0
    max_pages: int | None = None
