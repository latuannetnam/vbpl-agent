from typing import Any
from vbpl_kb.models import StatusObservation, AuthorityClassification, ApplicabilityEnvelope


def build_applicability(
    raw: dict[str, Any],
    status: StatusObservation,
    authority: AuthorityClassification,
    revision: str,
) -> ApplicabilityEnvelope:
    eff_from = raw.get("effFrom") or status.eff_from or ""
    eff_to = raw.get("effTo") or ""
    if eff_from is None:
        eff_from = ""
    if eff_to is None:
        eff_to = ""

    level = "unknown"
    transitional_until = ""

    order = authority.article4_order
    status_class = authority.classification_status

    if status_class == "legacy_transitional":
        level = "legacy_district"
        transitional_until = "2027-02-28T23:59:59+07:00"
    elif order is not None:
        if 1 <= order <= 9:
            level = "national"
        elif 10 <= order <= 12:
            level = "province"
        elif order == 13:
            level = "special_zone"
        elif 14 <= order <= 15:
            level = "commune"

    agency = authority.issuer_type or str(raw.get("agencyName", ""))
    jurisdiction_name = "national" if level == "national" else agency
    jurisdiction_code = level if level in ("national", "legacy_district") else agency.lower().replace(" ", "_")

    source_url = f"https://vbpl.vn/van-ban/chi-tiet/--{status.vbpl_id}"

    return ApplicabilityEnvelope(
        legal_status_raw=status.eff_status or str(raw.get("effStatus", "")),
        legal_status_normalized=status.eff_status,
        verified_at=status.checked_at.isoformat(),
        status_source=status.status_source,
        effective_from=str(eff_from),
        effective_to=str(eff_to),
        jurisdiction_level=level,  # type: ignore[arg-type]
        jurisdiction_code=jurisdiction_code,
        jurisdiction_name=jurisdiction_name,
        transitional_until=transitional_until,
        source_url=source_url,
        corpus_revision=revision,
        status_evidence_hash=status.content_hash,
    )
