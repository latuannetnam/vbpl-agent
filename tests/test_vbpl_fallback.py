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
