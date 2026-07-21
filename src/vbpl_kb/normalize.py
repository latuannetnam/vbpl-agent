import re
import unicodedata
from html import unescape
from html.parser import HTMLParser
from typing import Any
from vbpl_kb.models import StatusObservation, OnyxDocument

class _HTMLText(HTMLParser):
    _break_tags = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._break_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._break_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _html_to_text(html: str) -> str:
    parser = _HTMLText()
    parser.feed(html)
    text = unescape("".join(parser.parts)).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _slug(value: str) -> str:
    value = value.lower().replace("đ", "d")
    value = unicodedata.normalize("NFD", value)
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value)).strip("-")


def _content(raw: dict[str, Any]) -> str:
    document_content = raw.get("documentContent")
    if isinstance(document_content, dict) and isinstance(document_content.get("content"), str):
        return _html_to_text(document_content["content"])
    if isinstance(raw.get("fullText"), str):
        return raw["fullText"]
    return ""


def _render_provisions(text: str) -> tuple[str, str]:
    rendered: list[str] = []
    has_article = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^Điều\s+\d+(?:[.\s]|$)", line, re.IGNORECASE):
            rendered.append(f"## {line}")
            has_article = True
        elif re.match(r"^\d+\.\s+", line):
            number, body = line.split(".", 1)
            rendered.append(f"### Khoản {number}.{body}")
        elif re.match(r"^[a-zđ]\)\s+", line, re.IGNORECASE):
            point, body = line.split(")", 1)
            rendered.append(f"#### Điểm {point}.{body}")
        else:
            rendered.append(line)
    if not has_article:
        return f"## Toàn văn\n\n{text}", "unparsed"
    return "\n\n".join(rendered), "parsed"


def normalize_instrument(raw: dict[str, Any], status: StatusObservation, revision: str) -> OnyxDocument:
    vbpl_id = str(raw.get("id") or status.vbpl_id)
    title = raw.get("title") or f"Document {vbpl_id}"
    full_text = _content(raw)
    
    canonical_link = f"https://vbpl.vn/van-ban/chi-tiet/{_slug(title)}--{vbpl_id}"
    status_checked_at_iso = status.checked_at.isoformat()
    
    provenance = (
        f"Document ID: vbpl:{vbpl_id}\n"
        f"Title: {title}\n"
        f"Link: {canonical_link}\n"
        f"Status: {status.eff_status}\n"
        f"Verification Time: {status_checked_at_iso}\n"
        f"Corpus Revision: {revision}\n\n"
    )
    
    body, citation_structure = _render_provisions(full_text)
        
    content = provenance + body
    
    metadata = {
        "legal_status": status.eff_status,
        "status_checked_at": status_checked_at_iso,
        "effective_from": status.eff_from or "",
        "source_url": canonical_link,
        "corpus_revision": revision,
        "document_type": raw.get("docType", raw.get("documentType", "")),
        "legal_area": raw.get("legalArea", ""),
        "issuer": raw.get("agencyName", raw.get("issuer", "")),
        "scope": raw.get("scope", ""),
        "citation_structure": citation_structure,
        "document_number": raw.get("docNum", ""),
        "title": title,
    }
    
    return OnyxDocument(
        document_id=f"vbpl:{vbpl_id}",
        content=content,
        link=canonical_link,
        metadata=metadata
    )
