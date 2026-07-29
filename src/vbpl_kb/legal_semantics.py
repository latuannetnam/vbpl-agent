from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

REGIMES_DIR = Path(__file__).parent / "data" / "authority-regimes"


@dataclass(frozen=True)
class AuthorityClassificationResult:
    form: str
    issuer: str
    statutory_group: str
    order_string: str
    classification_version: str


@dataclass(frozen=True)
class EligibilityDecision:
    eligible: bool
    exclusion_reasons: list[str]


@dataclass(frozen=True)
class ApplicabilityEnvelopeDraft:
    status: str
    verified_at: datetime
    effective_from: date | None
    effective_to: date | None
    jurisdiction: str
    subject_tokens: list[str]
    is_current_eligible: bool
    exclusion_reasons: list[str]


@dataclass(frozen=True)
class LegalRelationDraft:
    id: str
    source_version_id: str
    source_node_id: str | None
    target_instrument_id: str | None
    target_version_id: str | None
    target_node_id: str | None
    relation_type: str
    direction: str
    is_verified_effect: bool
    quote: str | None
    evidence_hash: str | None
    confidence: float
    logical_edge_id: str
    effective_from: date | None
    effective_to: date | None


_regime_cache: dict[str, dict[str, Any]] = {}


def load_authority_regime(regime_id: str = "2025-07-01") -> dict[str, Any]:
    if regime_id not in _regime_cache:
        path = REGIMES_DIR / f"{regime_id}.json"
        if not path.exists():
            raise ValueError(f"Authority regime file not found: {path}")
        _regime_cache[regime_id] = json.loads(path.read_text(encoding="utf-8"))
    return _regime_cache[regime_id]


def classify_authority(
    normative_form: str,
    issuer: str,
    regime_id: str = "2025-07-01",
) -> AuthorityClassificationResult:
    regime = load_authority_regime(regime_id)
    groups = regime.get("groups", [])
    version = regime.get("regime_version", "2025.1")

    if isinstance(normative_form, dict):
        normative_form = str(normative_form.get("name") or "")
    if isinstance(issuer, dict):
        issuer = str(issuer.get("name") or "")

    norm_form_clean = str(normative_form or "").strip()
    issuer_clean = str(issuer or "").strip()

    matched_group = None
    for group in groups:
        forms = group.get("forms", [])
        issuers = group.get("issuers", [])

        if norm_form_clean in forms:
            if not issuers or issuer_clean in issuers or any(i.lower() in issuer_clean.lower() for i in issuers):
                matched_group = group
                break

    if not matched_group:
        order_num = 15
        group_name = "Văn bản khác"
    else:
        order_num = matched_group["order"]
        group_name = matched_group["name"]

    order_str = f"{order_num:02d}"

    return AuthorityClassificationResult(
        form=normative_form,
        issuer=issuer,
        statutory_group=group_name,
        order_string=order_str,
        classification_version=version,
    )


DEFAULT_FRESHNESS_WINDOW = timedelta(hours=24)
ELIGIBLE_STATUSES = {"còn hiệu lực", "hết hiệu lực một phần"}


def is_current_eligible(
    status: str | Any,
    verified_at: datetime | date | None = None,
    now: datetime | None = None,
    parse_status: str = "verified_structured",
    freshness: timedelta = DEFAULT_FRESHNESS_WINDOW,
) -> EligibilityDecision:
    now = now or datetime.now(timezone.utc)
    exclusion_reasons: list[str] = []

    if isinstance(status, dict):
        status = str(status.get("name") or "")

    status_lower = str(status or "").strip().lower()
    in_force_keywords = ["còn hiệu lực", "hết hiệu lực một phần"]
    if not any(k in status_lower for k in in_force_keywords):
        exclusion_reasons.append("expired_or_repealed")

    if verified_at is None:
        verified_at = now
    elif isinstance(verified_at, date) and not isinstance(verified_at, datetime):
        verified_at = datetime.combine(verified_at, datetime.min.time(), tzinfo=timezone.utc)

    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if (now - verified_at) > freshness:
        exclusion_reasons.append("stale_status")

    if parse_status in ("heuristic", "unparsed"):
        exclusion_reasons.append("heuristic_structure")

    eligible = len(exclusion_reasons) == 0
    return EligibilityDecision(eligible=eligible, exclusion_reasons=exclusion_reasons)


def build_applicability(
    status: str | Any,
    verified_at: datetime | date | None = None,
    effective_from: date | None = None,
    effective_to: date | None = None,
    jurisdiction: str = "national",
    subject_tokens: Sequence[str] | None = None,
    overrides: Sequence[Any] = (),
    now: datetime | None = None,
) -> ApplicabilityEnvelopeDraft:
    if isinstance(status, dict):
        status = str(status.get("name") or "")

    eligibility = is_current_eligible(status, verified_at, now=now)
    dt_verified = verified_at or datetime.now(timezone.utc)
    if isinstance(dt_verified, date) and not isinstance(dt_verified, datetime):
        dt_verified = datetime.combine(dt_verified, datetime.min.time(), tzinfo=timezone.utc)

    return ApplicabilityEnvelopeDraft(
        status=str(status or "").strip(),
        verified_at=dt_verified,
        effective_from=effective_from,
        effective_to=effective_to,
        jurisdiction=jurisdiction,
        subject_tokens=list(subject_tokens) if subject_tokens else [],
        is_current_eligible=eligibility.eligible,
        exclusion_reasons=eligibility.exclusion_reasons,
    )


def resolve_relations(
    source_version_id: str,
    source_node_id: str | None,
    raw_references: Sequence[Mapping[str, Any]],
) -> list[LegalRelationDraft]:
    relations: list[LegalRelationDraft] = []
    seen_edges: set[str] = set()

    for ref in raw_references:
        target_vbpl_id = str(ref.get("target_vbpl_id") or "")
        relation_type = str(ref.get("relation_type") or "cites")
        evidence_kind = str(ref.get("evidence_kind") or "text_candidate")
        quote = ref.get("quote")
        ev_hash = ref.get("evidence_hash")

        target_instrument_id = f"vbpl:{target_vbpl_id}" if target_vbpl_id else None
        direction = "forward"

        is_verified = evidence_kind in ("official_structured", "official_page")

        edge_raw = f"{source_version_id}\0{source_node_id}\0{target_instrument_id}\0{relation_type}".encode("utf-8")
        logical_edge_id = "edge:" + hashlib.sha256(edge_raw).hexdigest()

        if logical_edge_id in seen_edges:
            continue
        seen_edges.add(logical_edge_id)

        rel_id = "rel:" + hashlib.sha256(f"{logical_edge_id}\0{ev_hash}".encode("utf-8")).hexdigest()

        relations.append(
            LegalRelationDraft(
                id=rel_id,
                source_version_id=source_version_id,
                source_node_id=source_node_id,
                target_instrument_id=target_instrument_id,
                target_version_id=None,
                target_node_id=None,
                relation_type=relation_type,
                direction=direction,
                is_verified_effect=is_verified,
                quote=str(quote) if quote else None,
                evidence_hash=str(ev_hash) if ev_hash else None,
                confidence=1.0 if is_verified else 0.7,
                logical_edge_id=logical_edge_id,
                effective_from=None,
                effective_to=None,
            )
        )

    return relations
