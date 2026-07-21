import re
import json
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
_LEGAL_FORCE_MAP = {"InForce": "Còn hiệu lực", "PartiallyInForce": "Hết hiệu lực một phần", "OutOfForce": "Hết hiệu lực"}


def resolve_canonical_page(
    vbpl_id: str, html: str, checked_at: datetime
) -> FallbackResolution:
    for payload in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("@type") != "Legislation":
                continue
            title = entry.get("name")
            status = _LEGAL_FORCE_MAP.get(entry.get("legislationLegalForce"))
            if isinstance(title, str) and title.strip() and status:
                return FallbackResolution(True, title.strip(), status, "canonical_page", checked_at)
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
