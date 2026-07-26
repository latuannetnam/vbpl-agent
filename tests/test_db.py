from unittest.mock import MagicMock
import pytest
from pydantic import SecretStr

from vbpl_kb.config import Settings
from vbpl_kb.db import PipelineAlreadyRunning, create_engine, pipeline_advisory_lock


def test_settings_requires_database_url() -> None:
    settings = Settings(database_url=SecretStr("postgresql+psycopg://user:pass@localhost/db"))
    assert isinstance(settings.database_url, SecretStr)
    assert settings.database_url.get_secret_value() == "postgresql+psycopg://user:pass@localhost/db"
    assert settings.pipeline_lock_key == 868075126


def test_create_engine_fails_on_empty_database_url() -> None:
    with pytest.raises(ValueError, match="VBPL_KB_DATABASE_URL environment variable or setting must be set and non-empty"):
        create_engine(SecretStr(""))


def test_pipeline_advisory_lock_acquires_and_releases() -> None:
    mock_session = MagicMock()
    mock_session.scalar.return_value = True

    with pipeline_advisory_lock(mock_session, 868075126):
        mock_session.scalar.assert_called_once()

    mock_session.execute.assert_called_once()


def test_pipeline_advisory_lock_fails_fast_when_locked() -> None:
    mock_session = MagicMock()
    mock_session.scalar.return_value = False

    with pytest.raises(PipelineAlreadyRunning):
        with pipeline_advisory_lock(mock_session, 868075126):
            pass

    mock_session.execute.assert_not_called()
