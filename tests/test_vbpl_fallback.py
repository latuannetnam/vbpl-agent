from datetime import UTC, datetime

from vbpl_kb.vbpl_fallback import resolve_canonical_page


def test_canonical_page_resolves_explicit_title_and_legal_status() -> None:
    result = resolve_canonical_page(
        "123",
        "<h1>Nghị định số 1/2026/NĐ-CP</h1><div>Tình trạng hiệu lực: Còn hiệu lực</div>",
        datetime(2026, 7, 21, tzinfo=UTC),
    )

    assert result.verified is True
    assert result.title == "Nghị định số 1/2026/NĐ-CP"
    assert result.eff_status == "Còn hiệu lực"
    assert result.source_method == "canonical_page"


def test_canonical_page_quarantines_missing_explicit_legal_status() -> None:
    result = resolve_canonical_page(
        "123",
        "<h1>Nghị định số 1/2026/NĐ-CP</h1><div>Trạng thái: Publish</div>",
        datetime(2026, 7, 21, tzinfo=UTC),
    )

    assert result.verified is False
    assert result.reason == "missing explicit legal status"


def test_canonical_page_resolves_json_ld_legal_force() -> None:
    result = resolve_canonical_page(
        "117180",
        '<script type="application/ld+json">{"@type":"Legislation","name":"Quyết định 279","url":"https://vbpl.vn/van-ban/chi-tiet/q--117180","legislationLegalForce":"InForce"}</script>',
        datetime(2026, 7, 21, tzinfo=UTC),
    )

    assert result.verified is True
    assert result.title == "Quyết định 279"
    assert result.eff_status == "Còn hiệu lực"


def test_canonical_page_uses_official_body_heading_when_json_ld_title_is_blank() -> None:
    result = resolve_canonical_page(
        "173680",
        '<script type="application/ld+json">{"@type":"Legislation","name":"","legislationLegalForce":"InForce"}</script>',
        datetime(2026, 7, 21, tzinfo=UTC),
        {
            "documentContent": {
                "content": """
                    <p>Số: 13/2024/TT-BXD</p>
                    <p><strong>THÔNG TƯ</strong></p>
                    <p><strong>Quy trình, quy định kỹ thuật kiểm kê khí nhà kính</strong></p>
                    <p><em>Căn cứ Luật Bảo vệ môi trường;</em></p>
                """,
            }
        },
    )

    assert result.verified is True
    assert result.title == "Thông tư số 13/2024/TT-BXD: Quy trình, quy định kỹ thuật kiểm kê khí nhà kính"
    assert result.eff_status == "Còn hiệu lực"
