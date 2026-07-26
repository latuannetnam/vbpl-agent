from pathlib import Path
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from vbpl_kb.db_models import Base
from vbpl_kb.canonicalize import canonicalize_instrument
from vbpl_kb.legal_tree import LegalNodeDraft
from vbpl_kb.legal_semantics import (
    classify_authority,
    build_applicability,
    resolve_relations,
)
from vbpl_kb.projection import CanonicalBundle, project_current, project_history, project_evidence
from vbpl_kb.releases import ReleaseBuilder, ReleaseValidator, ReleaseManager
from vbpl_kb.repositories import CanonicalRepository


@pytest.fixture
def memory_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_publish_end_to_end_pipeline(memory_session, tmp_path: Path) -> None:
    detail_data = {
        "id": 5001,
        "title": "Nghị định quy định chi tiết",
        "docNum": "100/2026/NĐ-CP",
        "issueDate": "2026-01-01",
        "effDate": "2026-02-01",
        "effStatus": {"name": "Còn hiệu lực"},
    }
    draft = canonicalize_instrument(detail_data, "hash_payload", "hash_evidence")
    nodes = [
        LegalNodeDraft(
            node_type="article",
            display_label="Điều 1",
            normalized_coordinate="dieu-01",
            heading="Phạm vi",
            sibling_ordinal=1,
            materialized_path="dieu-01",
            text="Điều 1. Phạm vi điều chỉnh...",
            lead_in_text=None,
            source_anchor="dieu-01",
            source_start=0,
            source_end=20,
            content_hash="hash_node",
            parse_status="verified_structured",
        )
    ]

    canonical_repo = CanonicalRepository(memory_session)
    res = canonical_repo.upsert_observation(draft, nodes)
    assert res.is_new_version is True

    auth = classify_authority("Nghị định", "Chính phủ")
    app = build_applicability("Còn hiệu lực", verified_at=draft.issue_date or None)
    rels = resolve_relations(draft.version_id, None, [])

    bundle = CanonicalBundle(
        draft=draft,
        nodes=nodes,
        authority=auth,
        applicability=app,
        relations=rels,
    )

    now_dt = datetime.combine(draft.issue_date, datetime.min.time(), tzinfo=timezone.utc)
    cur_docs = list(project_current(bundle, now=now_dt))
    hist_docs = list(project_history(bundle))
    ev_docs = list(project_evidence(bundle))

    sample_docs = {
        "current": [d.to_dict() for d in cur_docs],
        "history": [d.to_dict() for d in hist_docs],
        "evidence": [d.to_dict() for d in ev_docs],
    }

    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    builder = ReleaseBuilder(export_dir)
    manifest = builder.build_candidate("rev-test", sample_documents=sample_docs)

    validator = ReleaseValidator(export_dir)
    report = validator.validate(manifest)
    assert report.is_valid is True

    manager = ReleaseManager(export_dir)
    active = manager.promote(manifest)
    assert active.release_id == manifest.release_id
