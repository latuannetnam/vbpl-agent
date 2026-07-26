from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import re
from typing import Any, Literal, Mapping, Sequence

NodeType = Literal["part", "chapter", "article", "clause", "point"]
ParseStatus = Literal["verified_structured", "verified_text", "heuristic", "unparsed"]


@dataclass(frozen=True)
class LegalNodeDraft:
    node_type: NodeType
    display_label: str
    normalized_coordinate: str
    heading: str | None
    sibling_ordinal: int
    materialized_path: str
    text: str
    lead_in_text: str | None
    source_anchor: str | None
    source_start: int | None
    source_end: int | None
    content_hash: str
    parse_status: ParseStatus


def normalize_vietnamese_number(val: str) -> str:
    # Convert Roman or Arabic numbers to two-digit string e.g. 1 -> 01, II -> 02, III -> 03
    roman_map = {
        "i": "01", "ii": "02", "iii": "03", "iv": "04", "v": "05",
        "vi": "06", "vii": "07", "viii": "08", "ix": "09", "x": "10",
        "xi": "11", "xii": "12", "xiii": "13", "xiv": "14", "xv": "15"
    }
    clean = val.strip().lower().rstrip(".")
    if clean in roman_map:
        return roman_map[clean]
    if clean.isdigit():
        return f"{int(clean):02d}"
    return clean


def parse_legal_tree(detail: Mapping[str, Any], evidence: bytes) -> tuple[LegalNodeDraft, ...]:
    text_content = evidence.decode("utf-8", errors="replace")

    # 1. Structured HTML parsing if HTML tags exist
    if "<div" in text_content or "<h" in text_content or "<p" in text_content:
        nodes = _parse_html_structure(text_content)
        if nodes:
            return tuple(nodes)

    # 2. Text regex parsing fallback
    full_text = detail.get("fullText") or text_content
    if isinstance(full_text, str) and full_text.strip():
        nodes = _parse_text_regex(full_text)
        if nodes:
            return tuple(nodes)

    # 3. Unparsed single node fallback
    content_hash = hashlib.sha256(text_content.encode()).hexdigest()
    return (
        LegalNodeDraft(
            node_type="article",
            display_label="Văn bản",
            normalized_coordinate="dieu-00",
            heading=None,
            sibling_ordinal=1,
            materialized_path="dieu-00",
            text=text_content[:2000],
            lead_in_text=None,
            source_anchor=None,
            source_start=0,
            source_end=len(text_content),
            content_hash=content_hash,
            parse_status="unparsed",
        ),
    )


class _VBPLHTMLTreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[dict[str, Any]] = []
        self.nodes: list[LegalNodeDraft] = []
        self.current_tag: str | None = None
        self.current_attrs: dict[str, str] = {}
        self.current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str]]) -> None:
        attr_dict = dict(attrs)
        self.current_tag = tag
        self.current_attrs = attr_dict

    def handle_data(self, data: str) -> None:
        txt = data.strip()
        if txt:
            self.current_text.append(txt)


def _parse_html_structure(html_str: str) -> list[LegalNodeDraft]:
    nodes: list[LegalNodeDraft] = []

    # Regex patterns for headers and provisions in HTML
    part_pat = re.compile(r"Phần\s+([I|V|X|i|v|x|\d]+)[\.\:]?\s*(.*)", re.IGNORECASE)
    chap_pat = re.compile(r"Chương\s+([I|V|X|i|v|x|\d]+)[\.\:]?\s*(.*)", re.IGNORECASE)
    art_pat = re.compile(r"Điều\s+(\d+)\.[\:]?\s*(.*)", re.IGNORECASE)
    clause_pat = re.compile(r"^(\d+)\.\s+(.*)")
    point_pat = re.compile(r"^([a-zđ])\)\s+(.*)", re.IGNORECASE)

    # Simple element extractor over standard HTML
    paragraphs = re.findall(r"<(?:h\d|p|div)[^>]*>(.*?)</(?:h\d|p|div)>", html_str, re.DOTALL | re.IGNORECASE)
    if not paragraphs:
        paragraphs = [p.strip() for p in html_str.split("\n") if p.strip()]

    current_part: str | None = None
    current_chap: str | None = None
    current_art: str | None = None
    current_clause: str | None = None

    part_ord = 0
    chap_ord = 0
    art_ord = 0
    clause_ord = 0
    point_ord = 0

    for raw_p in paragraphs:
        p_text = re.sub(r"<[^>]+>", "", raw_p).strip()
        if not p_text:
            continue

        # Check Part
        m_part = part_pat.search(p_text)
        if m_part:
            part_num = normalize_vietnamese_number(m_part.group(1))
            current_part = f"phan-{part_num}"
            current_chap = None
            current_art = None
            current_clause = None
            part_ord += 1
            chap_ord = 0
            art_ord = 0
            clause_ord = 0
            point_ord = 0

            nodes.append(
                LegalNodeDraft(
                    node_type="part",
                    display_label=f"Phần {m_part.group(1)}",
                    normalized_coordinate=current_part,
                    heading=m_part.group(2) or None,
                    sibling_ordinal=part_ord,
                    materialized_path=current_part,
                    text=p_text,
                    lead_in_text=None,
                    source_anchor=current_part,
                    source_start=None,
                    source_end=None,
                    content_hash=hashlib.sha256(p_text.encode()).hexdigest(),
                    parse_status="verified_structured",
                )
            )
            continue

        # Check Chapter
        m_chap = chap_pat.search(p_text)
        if m_chap:
            chap_num = normalize_vietnamese_number(m_chap.group(1))
            current_chap = f"chuong-{chap_num}"
            current_art = None
            current_clause = None
            chap_ord += 1
            art_ord = 0
            clause_ord = 0
            point_ord = 0

            path = f"{current_part}/{current_chap}" if current_part else current_chap

            nodes.append(
                LegalNodeDraft(
                    node_type="chapter",
                    display_label=f"Chương {m_chap.group(1)}",
                    normalized_coordinate=current_chap,
                    heading=m_chap.group(2) or None,
                    sibling_ordinal=chap_ord,
                    materialized_path=path,
                    text=p_text,
                    lead_in_text=None,
                    source_anchor=current_chap,
                    source_start=None,
                    source_end=None,
                    content_hash=hashlib.sha256(p_text.encode()).hexdigest(),
                    parse_status="verified_structured",
                )
            )
            continue

        # Check Article
        m_art = art_pat.search(p_text)
        if m_art:
            art_num = normalize_vietnamese_number(m_art.group(1))
            current_art = f"dieu-{art_num}"
            current_clause = None
            art_ord += 1
            clause_ord = 0
            point_ord = 0

            ancestors = [x for x in [current_part, current_chap, current_art] if x]
            path = "/".join(ancestors)

            nodes.append(
                LegalNodeDraft(
                    node_type="article",
                    display_label=f"Điều {m_art.group(1)}",
                    normalized_coordinate=current_art,
                    heading=m_art.group(2) or None,
                    sibling_ordinal=art_ord,
                    materialized_path=path,
                    text=p_text,
                    lead_in_text=None,
                    source_anchor=current_art,
                    source_start=None,
                    source_end=None,
                    content_hash=hashlib.sha256(p_text.encode()).hexdigest(),
                    parse_status="verified_structured",
                )
            )
            continue

        # Check Clause
        m_clause = clause_pat.search(p_text)
        if m_clause and current_art:
            clause_num = normalize_vietnamese_number(m_clause.group(1))
            current_clause = f"khoan-{clause_num}"
            clause_ord += 1
            point_ord = 0

            ancestors = [x for x in [current_part, current_chap, current_art, current_clause] if x]
            path = "/".join(ancestors)

            nodes.append(
                LegalNodeDraft(
                    node_type="clause",
                    display_label=f"Khoản {m_clause.group(1)}",
                    normalized_coordinate=current_clause,
                    heading=None,
                    sibling_ordinal=clause_ord,
                    materialized_path=path,
                    text=p_text,
                    lead_in_text=None,
                    source_anchor=current_clause,
                    source_start=None,
                    source_end=None,
                    content_hash=hashlib.sha256(p_text.encode()).hexdigest(),
                    parse_status="verified_structured",
                )
            )
            continue

        # Check Point
        m_point = point_pat.search(p_text)
        if m_point and current_art and current_clause:
            point_let = m_point.group(1).lower()
            current_point = f"diem-{point_let}"
            point_ord += 1

            ancestors = [x for x in [current_part, current_chap, current_art, current_clause, current_point] if x]
            path = "/".join(ancestors)

            nodes.append(
                LegalNodeDraft(
                    node_type="point",
                    display_label=f"Điểm {point_let}",
                    normalized_coordinate=current_point,
                    heading=None,
                    sibling_ordinal=point_ord,
                    materialized_path=path,
                    text=p_text,
                    lead_in_text=None,
                    source_anchor=current_point,
                    source_start=None,
                    source_end=None,
                    content_hash=hashlib.sha256(p_text.encode()).hexdigest(),
                    parse_status="verified_structured",
                )
            )
            continue

    return nodes


def _parse_text_regex(text_str: str) -> list[LegalNodeDraft]:
    nodes: list[LegalNodeDraft] = []
    art_splits = re.split(r"\n(?=Điều\s+\d+[\.\:])", text_str)

    art_ord = 0
    for block in art_splits:
        block_strip = block.strip()
        if not block_strip:
            continue
        m_art = re.match(r"Điều\s+(\d+)[\.\:]?\s*(.*)", block_strip)
        if m_art:
            art_ord += 1
            art_num = normalize_vietnamese_number(m_art.group(1))
            coord = f"dieu-{art_num}"

            nodes.append(
                LegalNodeDraft(
                    node_type="article",
                    display_label=f"Điều {m_art.group(1)}",
                    normalized_coordinate=coord,
                    heading=m_art.group(2).split("\n")[0] if m_art.group(2) else None,
                    sibling_ordinal=art_ord,
                    materialized_path=coord,
                    text=block_strip,
                    lead_in_text=None,
                    source_anchor=coord,
                    source_start=None,
                    source_end=None,
                    content_hash=hashlib.sha256(block_strip.encode()).hexdigest(),
                    parse_status="verified_text",
                )
            )
    return nodes
