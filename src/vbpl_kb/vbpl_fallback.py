import re
from dataclasses import dataclass
from datetime import datetime

from vbpl_kb.normalize import _html_to_text


@dataclass(frozen=True)
class FallbackResolution:
    verified: bool
    title: str | None
    eff_status: str | None
    source_method: str
    checked_at: datetime
    reason: str | None = None


_LEGAL_STATUSES = ("Còn hiệu lực", "Hết hiệu lực một phần", "Hết hiệu lực")


def resolve_canonical_page(
    vbpl_id: str, html: str, checked_at: datetime
) -> FallbackResolution:
    text = _html_to_text(html)
    title_match = re.search(r"(?:^|\n)([^\n]+)", text)
    title = title_match.group(1).strip() if title_match else None
    status_match = re.search(
        r"Tình trạng hiệu lực\s*:\s*(Còn hiệu lực|Hết hiệu lực một phần|Hết hiệu lực)",
        text,
        re.IGNORECASE,
    )
    if not status_match:
        return FallbackResolution(False, title, None, "canonical_page", checked_at, "missing explicit legal status")
    status = next(value for value in _LEGAL_STATUSES if value.casefold() == status_match.group(1).casefold())
    if not title:
        return FallbackResolution(False, None, status, "canonical_page", checked_at, "missing explicit title")
    return FallbackResolution(True, title, status, "canonical_page", checked_at)
