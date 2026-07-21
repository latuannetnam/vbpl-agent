import json
from pathlib import Path
import pytest
from vbpl_kb.config import Settings

from pydantic import SecretStr

@pytest.fixture
def settings() -> Settings:
    return Settings(
        vbpl_gateway_url="https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public",
        onyx_base_url="http://localhost:8080",
        onyx_api_key=SecretStr("test-key"),
        data_dir=Path("data"),
        freshness_hours=24
    )

@pytest.fixture
def load_fixture():
    def _load(name: str):
        path = Path(__file__).parent / "fixtures" / "vbpl" / name
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return _load
