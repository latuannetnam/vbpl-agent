from contextlib import contextmanager
from typing import Iterator
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine as _sa_create_engine, text
from sqlalchemy.orm import Session, sessionmaker


class PipelineAlreadyRunning(Exception):
    """Raised when another VBPL pipeline run holds the PostgreSQL advisory lock."""
    pass


def create_engine(database_url: SecretStr) -> Engine:
    url_str = database_url.get_secret_value()
    if not url_str:
        raise ValueError("VBPL_KB_DATABASE_URL environment variable or setting must be set and non-empty")
    return _sa_create_engine(url_str, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def pipeline_advisory_lock(session: Session, lock_key: int) -> Iterator[None]:
    acquired = session.scalar(
        text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
    )
    if acquired is not True:
        raise PipelineAlreadyRunning("another VBPL pipeline run holds the lock")
    try:
        yield
    finally:
        session.execute(
            text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key}
        )
