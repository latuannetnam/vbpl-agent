import os
import pytest
import sqlalchemy
from alembic import command
from alembic.config import Config


EXPECTED_TABLES = {
    "pipeline_runs",
    "catalog_scans",
    "catalog_observations",
    "removal_candidates",
    "evidence_objects",
    "evidence_dependencies",
    "instruments",
    "instrument_versions",
    "legal_nodes",
    "authority_regimes",
    "authority_classifications",
    "status_observations",
    "applicability_envelopes",
    "legal_relations",
    "release_runs",
    "release_views",
    "connector_deliveries",
    "acceptance_runs",
}

LEGACY_TABLES = {
    "raw_snapshots",
    "catalog",
    "releases",
    "corpus_versions",
    "provisions",
}


@pytest.mark.postgres
def test_alembic_migration_head_creates_expected_schema() -> None:
    database_url = os.environ.get("VBPL_KB_DATABASE_URL")
    if not database_url:
        pytest.skip("VBPL_KB_DATABASE_URL environment variable is not set")

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)

    # First migration run
    command.upgrade(alembic_cfg, "head")

    engine = sqlalchemy.create_engine(database_url)
    inspector = sqlalchemy.inspect(engine)
    tables = set(inspector.get_table_names())

    assert EXPECTED_TABLES.issubset(tables), f"Missing tables: {EXPECTED_TABLES - tables}"
    assert LEGACY_TABLES.isdisjoint(tables), f"Legacy tables found: {LEGACY_TABLES & tables}"

    # Second migration run (idempotent check)
    command.upgrade(alembic_cfg, "head")

    tables_after = set(inspector.get_table_names())
    assert tables == tables_after
