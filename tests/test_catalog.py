import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from vbpl_kb.db_models import Base
from vbpl_kb.models import CatalogEntry
from vbpl_kb.repositories import CatalogRepository


@pytest.fixture
def memory_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_catalog_repository_two_scan_removal(memory_session) -> None:
    repo = CatalogRepository(memory_session)

    # Scan 1: contains doc 101 and 102
    scan1_id = repo.begin_scan()
    entries1 = [
        CatalogEntry(vbpl_id="101", title="Doc 101"),
        CatalogEntry(vbpl_id="102", title="Doc 102"),
    ]
    changes1 = repo.complete_scan(scan1_id, entries1)
    assert set(changes1.upsert_ids) == {101, 102}

    # Scan 2: doc 102 is missing (first complete absence -> removal candidate)
    scan2_id = repo.begin_scan()
    entries2 = [
        CatalogEntry(vbpl_id="101", title="Doc 101"),
    ]
    changes2 = repo.complete_scan(scan2_id, entries2)
    assert changes2.removal_candidate_ids == [102]
    assert changes2.tombstone_ids == []

    # Scan 3 (partial/failed): should NOT increment absence count
    scan3_id = repo.begin_scan()
    repo.fail_scan(scan3_id, "Network timeout on page 2")

    # Scan 4: doc 102 missing again (second consecutive complete absence -> tombstone)
    scan4_id = repo.begin_scan()
    entries4 = [
        CatalogEntry(vbpl_id="101", title="Doc 101"),
    ]
    changes4 = repo.complete_scan(scan4_id, entries4)
    assert changes4.tombstone_ids == [102]

    # Scan 5: doc 102 reappears -> cleared candidate
    scan5_id = repo.begin_scan()
    entries5 = [
        CatalogEntry(vbpl_id="101", title="Doc 101"),
        CatalogEntry(vbpl_id="102", title="Doc 102"),
    ]
    changes5 = repo.complete_scan(scan5_id, entries5)
    assert changes5.cleared_ids == [102]
