from datetime import datetime, UTC
import pytest
from vbpl_kb.models import StatusObservation
from vbpl_kb.authority import classify_authority, AuthorityClassification
from vbpl_kb.applicability import build_applicability


@pytest.fixture
def status() -> StatusObservation:
    return StatusObservation(
        vbpl_id="178717",
        eff_status="Còn hiệu lực",
        eff_from="2025-07-01T00:00:00",
        checked_at=datetime(2026, 7, 24, 8, 0, 0, tzinfo=UTC),
        content_hash="a" * 64,
        run_id="vbpl-2026-07-24",
        status_source="api",
    )


def test_national_law_carries_status_evidence_and_effective_range(status: StatusObservation) -> None:
    envelope = build_applicability(
        {
            "effFrom": "2025-07-01T00:00:00",
            "effTo": None,
            "agencyName": "Quốc hội",
        },
        status,
        AuthorityClassification(
            hierarchy_regime="vn-vbqppl-2025-07-01",
            article4_order=2,
            normative_form="luat",
            authority_group="national_assembly_law",
            issuer_type="quoc_hoi",
            classification_status="known",
            classification_source="official_form+issuer",
            classification_version="article4-87-2025-v1",
            is_normative=True,
        ),
        "vbpl-2026-07-24",
    )
    assert envelope.jurisdiction_level == "national"
    assert envelope.effective_from == "2025-07-01T00:00:00"
    assert envelope.status_evidence_hash == status.content_hash


def test_legacy_district_transition_has_hard_end(status: StatusObservation) -> None:
    authority = classify_authority("Quyết định", "Ủy ban nhân dân huyện Đông Anh")
    envelope = build_applicability(
        {"agencyName": "Ủy ban nhân dân huyện Đông Anh"},
        status,
        authority,
        "vbpl-2026-07-24",
    )
    assert envelope.jurisdiction_level == "legacy_district"
    assert envelope.transitional_until == "2027-02-28T23:59:59+07:00"
