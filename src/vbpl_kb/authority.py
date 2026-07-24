import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from vbpl_kb.models import AuthorityClassification

HIERARCHY_REGIME = "vn-vbqppl-2025-07-01"
CLASSIFICATION_VERSION = "article4-87-2025-v1"


def _remove_accents(text: str) -> str:
    if not text:
        return ""
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    return stripped.lower().strip()


@dataclass(frozen=True)
class AuthorityRule:
    order: int
    group: str
    forms: tuple[str, ...]
    issuers: tuple[str, ...]
    match_any_two_issuers: bool = False


ARTICLE4_RULES: tuple[AuthorityRule, ...] = (
    AuthorityRule(1, "constitution", ("hien phap",), ("quoc hoi",)),
    AuthorityRule(2, "national_assembly_law", ("bo luat", "luat", "nghi quyet"), ("quoc hoi",)),
    AuthorityRule(3, "standing_committee", ("phap lenh", "nghi quyet", "nghi quyet lien tich"), ("uy ban thuong vu quoc hoi",)),
    AuthorityRule(4, "president", ("lenh", "quyet dinh"), ("chu tich nuoc",)),
    AuthorityRule(5, "government", ("nghi dinh", "nghi quyet", "nghi quyet lien tich"), ("chinh phu",)),
    AuthorityRule(6, "prime_minister", ("quyet dinh",), ("thu tuong chinh phu",)),
    AuthorityRule(7, "supreme_court_council", ("nghi quyet",), ("hoi dong tham phan toa an nhan dan toi cao",)),
    AuthorityRule(
        8,
        "authorized_central_circular",
        ("thong tu",),
        (
            "chanh an toa an nhan dan toi cao",
            "vien truong vien kiem sat nhan dan toi cao",
            "bo truong",
            "thu truong co quan ngang bo",
            "tong kiem toan nha nuoc",
        ),
    ),
    AuthorityRule(
        9,
        "joint_circular",
        ("thong tu lien tich",),
        ("chanh an", "vien truong", "tong kiem toan", "bo truong", "thu truong co quan ngang bo"),
        match_any_two_issuers=True,
    ),
    AuthorityRule(10, "provincial_council", ("nghi quyet",), ("hoi dong nhan dan tinh", "hoi dong nhan dan thanh pho")),
    AuthorityRule(11, "provincial_committee", ("quyet dinh",), ("uy ban nhan dan tinh", "uy ban nhan dan thanh pho")),
    AuthorityRule(12, "provincial_chair", ("quyet dinh",), ("chu tich uy ban nhan dan tinh", "chu tich uy ban nhan dan thanh pho")),
    AuthorityRule(13, "special_zone", ("van ban quy pham phap luat",), ("chinh quyen dac khu", "don vi hanh chinh kinh te dac biet")),
    AuthorityRule(14, "commune_council", ("nghi quyet",), ("hoi dong nhan dan xa", "hoi dong nhan dan phuong", "hoi dong nhan dan dac khu")),
    AuthorityRule(15, "commune_committee", ("quyet dinh",), ("uy ban nhan dan xa", "uy ban nhan dan phuong", "uy ban nhan dan dac khu")),
)


def classify_authority(
    document_type: str | dict[str, Any] | None,
    issuer: str | dict[str, Any] | None,
) -> AuthorityClassification:
    normative_form = ""
    parent_code = None

    if isinstance(document_type, dict):
        normative_form = str(document_type.get("name", ""))
        parent_code = document_type.get("parentCode")
    elif isinstance(document_type, str):
        normative_form = document_type

    issuer_str = ""
    if isinstance(issuer, dict):
        issuer_str = str(issuer.get("name", ""))
    elif isinstance(issuer, str):
        issuer_str = issuer

    if parent_code is not None and str(parent_code).upper() != "VBQPPL":
        return AuthorityClassification(
            hierarchy_regime=HIERARCHY_REGIME,
            article4_order=None,
            normative_form=normative_form,
            authority_group="not_normative",
            issuer_type=issuer_str,
            classification_status="not_normative",
            classification_source="official_form+parentCode",
            classification_version=CLASSIFICATION_VERSION,
            is_normative=False,
        )

    norm_form_clean = _remove_accents(normative_form)
    norm_issuer_clean = _remove_accents(issuer_str)

    district_patterns = [r"\bhuyen\b", r"\bquan\b", r"\bthi xa\b"]
    is_district_legacy = any(re.search(pat, norm_issuer_clean) for pat in district_patterns)
    if is_district_legacy:
        return AuthorityClassification(
            hierarchy_regime=HIERARCHY_REGIME,
            article4_order=None,
            normative_form=normative_form,
            authority_group="legacy_transitional",
            issuer_type=issuer_str,
            classification_status="legacy_transitional",
            classification_source="official_issuer_district",
            classification_version=CLASSIFICATION_VERSION,
            is_normative=True,
        )

    evaluation_order = [1, 2, 3, 4, 6, 5, 7, 9, 8, 12, 11, 10, 13, 14, 15]
    rule_by_order = {r.order: r for r in ARTICLE4_RULES}

    for order_key in evaluation_order:
        rule = rule_by_order[order_key]

        form_matched = any(f in norm_form_clean for f in rule.forms)
        if not form_matched:
            continue

        if rule.match_any_two_issuers:
            matches = sum(1 for iss in rule.issuers if iss in norm_issuer_clean)
            if matches >= 2 or "lien tich" in norm_form_clean:
                return AuthorityClassification(
                    hierarchy_regime=HIERARCHY_REGIME,
                    article4_order=rule.order,
                    normative_form=normative_form,
                    authority_group=rule.group,
                    issuer_type=issuer_str,
                    classification_status="known",
                    classification_source="official_form+issuer",
                    classification_version=CLASSIFICATION_VERSION,
                    is_normative=True,
                )
        else:
            issuer_matched = any(iss in norm_issuer_clean for iss in rule.issuers)
            if issuer_matched:
                return AuthorityClassification(
                    hierarchy_regime=HIERARCHY_REGIME,
                    article4_order=rule.order,
                    normative_form=normative_form,
                    authority_group=rule.group,
                    issuer_type=issuer_str,
                    classification_status="known",
                    classification_source="official_form+issuer",
                    classification_version=CLASSIFICATION_VERSION,
                    is_normative=True,
                )

    return AuthorityClassification(
        hierarchy_regime=HIERARCHY_REGIME,
        article4_order=None,
        normative_form=normative_form,
        authority_group="unknown",
        issuer_type=issuer_str,
        classification_status="unknown",
        classification_source="unmatched",
        classification_version=CLASSIFICATION_VERSION,
        is_normative=True,
    )
