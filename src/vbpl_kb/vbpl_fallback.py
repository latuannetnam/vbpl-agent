import re
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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


def _title_from_official_body(detail_data: dict[str, Any] | None) -> str | None:
    if not isinstance(detail_data, dict):
        return None
    document_content = detail_data.get("documentContent")
    if not isinstance(document_content, dict) or not isinstance(document_content.get("content"), str):
        return None
    lines = [line.strip() for line in _html_to_text(document_content["content"]).splitlines() if line.strip()]
    number_index = next((index for index, line in enumerate(lines) if re.match(r"^Số\s*:\s*\S+", line, re.IGNORECASE)), None)
    if number_index is None:
        return None
    number_match = re.match(r"^Số\s*:\s*(.+)$", lines[number_index], re.IGNORECASE)
    if number_match is None:
        return None
    document_type_index = number_index + 1
    while document_type_index < len(lines) and not re.fullmatch(r"[A-ZÀ-ỴĐ ]+", lines[document_type_index]):
        document_type_index += 1
    if document_type_index >= len(lines):
        return None
    heading_lines: list[str] = []
    for line in lines[document_type_index + 1:]:
        if re.match(r"^(Căn cứ|Theo đề nghị|Bộ trưởng|Chính phủ)", line, re.IGNORECASE):
            break
        heading_lines.append(line)
    if not heading_lines:
        return None
    document_type = lines[document_type_index].capitalize()
    heading = " ".join(heading_lines)
    return f"{document_type} số {number_match.group(1).strip()}: {heading}"


def resolve_canonical_page(
    vbpl_id: str, html: str, checked_at: datetime, detail_data: dict[str, Any] | None = None
) -> FallbackResolution:
    json_ld_status: str | None = None
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
            force = entry.get("legislationLegalForce")
            status = _LEGAL_FORCE_MAP.get(force) if isinstance(force, str) else None
            if status:
                json_ld_status = status
            if isinstance(title, str) and title.strip() and status:
                return FallbackResolution(True, title.strip(), status, "canonical_page", checked_at)
    if json_ld_status:
        title = _title_from_official_body(detail_data)
        if title:
            return FallbackResolution(True, title, json_ld_status, "canonical_page", checked_at)
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
