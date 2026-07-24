import pytest
from vbpl_kb.authority import classify_authority


@pytest.mark.parametrize(
    ("form", "issuer", "order", "group"),
    [
        ("Hiến pháp", "Quốc hội", 1, "constitution"),
        ("Luật", "Quốc hội", 2, "national_assembly_law"),
        ("Pháp lệnh", "Ủy ban Thường vụ Quốc hội", 3, "standing_committee"),
        ("Lệnh", "Chủ tịch nước", 4, "president"),
        ("Nghị định", "Chính phủ", 5, "government"),
        ("Quyết định", "Thủ tướng Chính phủ", 6, "prime_minister"),
        ("Nghị quyết", "Hội đồng Thẩm phán Tòa án nhân dân tối cao", 7, "supreme_court_council"),
        ("Thông tư", "Bộ trưởng Bộ Tư pháp", 8, "authorized_central_circular"),
        ("Thông tư liên tịch", "Bộ trưởng Bộ Tư pháp và Chánh án TANDTC", 9, "joint_circular"),
        ("Nghị quyết", "Hội đồng nhân dân tỉnh Bắc Ninh", 10, "provincial_council"),
        ("Quyết định", "Ủy ban nhân dân tỉnh Bắc Ninh", 11, "provincial_committee"),
        ("Quyết định", "Chủ tịch Ủy ban nhân dân tỉnh Bắc Ninh", 12, "provincial_chair"),
        ("Văn bản quy phạm pháp luật", "Chính quyền đặc khu Vân Đồn", 13, "special_zone"),
        ("Nghị quyết", "Hội đồng nhân dân phường Ba Đình", 14, "commune_council"),
        ("Quyết định", "Ủy ban nhân dân xã Minh Tân", 15, "commune_committee"),
    ],
)
def test_classifies_all_article_4_groups(form: str, issuer: str, order: int, group: str) -> None:
    result = classify_authority(form, issuer)
    assert result.article4_order == order
    assert result.authority_group == group
    assert result.classification_status == "known"
    assert result.hierarchy_regime == "vn-vbqppl-2025-07-01"


def test_structured_form_and_issuer_sensitive_decision() -> None:
    result = classify_authority(
        {"name": "Quyết định", "code": "QD", "parentCode": "VBQPPL"},
        "Chủ tịch Ủy ban nhân dân tỉnh Bắc Ninh",
    )
    assert result.article4_order == 12


def test_non_normative_parent_code_is_not_guessed_from_title() -> None:
    result = classify_authority(
        {"name": "Công văn", "code": "CV", "parentCode": "VBHC"},
        "Bộ Tư pháp",
    )
    assert result.classification_status == "not_normative"
    assert result.is_normative is False


def test_legacy_district_is_explicit() -> None:
    result = classify_authority("Quyết định", "Ủy ban nhân dân huyện Đông Anh")
    assert result.classification_status == "legacy_transitional"
    assert result.article4_order is None
