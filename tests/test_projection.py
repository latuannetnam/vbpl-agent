from datetime import datetime, timezone
import pytest
from vbpl_kb.projection import (
    CanonicalBundle,
    project_current,
    project_history,
    project_evidence,
)
from vbpl_kb.canonicalize import CanonicalInstrumentDraft
from vbpl_kb.legal_semantics import AuthorityClassificationResult, ApplicabilityEnvelopeDraft
from vbpl_kb.legal_tree import LegalNodeDraft


@pytest.fixture
def sample_bundle() -> CanonicalBundle:
    draft = CanonicalInstrumentDraft(
        instrument_id="vbpl:12345",
        official_source_id="12345",
        title="Luật Quản lý thuế",
        number="38/2019/QH14",
        issue_date=None,
        effective_date=None,
        current_status="Còn hiệu lực",
        detail_payload_hash="payload_hash_123",
        normalized_content_hash="norm_hash_123",
        raw_evidence_hash="ev_hash_123",
        version_id="ver:abc123ver",
    )
    nodes = [
        LegalNodeDraft(
            node_type="article",
            display_label="Điều 12",
            normalized_coordinate="dieu-12",
            heading="Hồ sơ khai thuế",
            sibling_ordinal=1,
            materialized_path="dieu-12",
            text="Điều 12. Hồ sơ khai thuế bao gồm các tài liệu sau...",
            lead_in_text=None,
            source_anchor="dieu-12",
            source_start=0,
            source_end=50,
            content_hash="content_hash_12",
            parse_status="verified_structured",
        )
    ]
    authority = AuthorityClassificationResult(
        form="Luật",
        issuer="Quốc hội",
        statutory_group="Bộ luật, Luật, Nghị quyết của Quốc hội",
        order_string="02",
        classification_version="2025.1",
    )
    applicability = ApplicabilityEnvelopeDraft(
        status="Còn hiệu lực",
        verified_at=datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
        effective_from=None,
        effective_to=None,
        jurisdiction="national",
        subject_tokens=["thue"],
        is_current_eligible=True,
        exclusion_reasons=[],
    )
    return CanonicalBundle(
        draft=draft,
        nodes=nodes,
        authority=authority,
        applicability=applicability,
        relations=[],
    )


def test_project_current_one_section_invariant_and_metadata(sample_bundle) -> None:
    now = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)
    docs = list(project_current(sample_bundle, now))

    assert len(docs) > 0
    for doc in docs:
        # Exactly one section per document
        assert len(doc.sections) == 1
        assert doc.document_id.startswith("vbpl:12345:current:")

        # Section text must include compact embedded header
        section_text = doc.sections[0].text
        assert "Văn bản: Luật Quản lý thuế" in section_text
        assert "Số: 38/2019/QH14" in section_text

        # Metadata values must only be str or list[str]
        for key, val in doc.metadata.items():
            assert isinstance(val, (str, list)), f"Metadata key {key} has non-string/non-list type: {type(val)}"
            if isinstance(val, list):
                assert all(isinstance(x, str) for x in val), f"List metadata key {key} contains non-string item"


def test_project_current_emits_no_evidence_documents(sample_bundle) -> None:
    now = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)
    docs = list(project_current(sample_bundle, now))
    assert not any(":evidence:" in doc.document_id for doc in docs)


def test_project_evidence_emits_evidence_documents(sample_bundle) -> None:
    docs = list(project_evidence(sample_bundle))
    assert len(docs) > 0
    for doc in docs:
        assert len(doc.sections) == 1
        assert ":evidence:" in doc.document_id
