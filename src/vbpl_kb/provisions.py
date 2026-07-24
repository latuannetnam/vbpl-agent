import re
import html
from vbpl_kb.models import Provision


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(cleaned)


def split_provisions(text: str) -> tuple[Provision, ...]:
    plain_text = _strip_html(text).strip()
    if not plain_text:
        return ()

    lines = [line.strip() for line in plain_text.splitlines() if line.strip()]

    has_dieu = any(re.match(r"^Điều\s+\d+", line) for line in lines)
    if not has_dieu:
        return (
            Provision(
                provision_key="toan-van",
                article_number="",
                clause_number="",
                point_label="",
                provision_heading="Toàn văn",
                citation_structure="unparsed",
                text=plain_text,
            ),
        )

    provisions: list[Provision] = []
    seen_keys: dict[str, int] = {}

    def add_provision(
        key: str,
        art_num: str,
        cl_num: str,
        pt_lbl: str,
        heading: str,
        cit_struct: str,
        body_lines: list[str],
    ) -> None:
        if not body_lines:
            return
        base_key = key
        if base_key in seen_keys:
            seen_keys[base_key] += 1
            final_key = f"{base_key}~{seen_keys[base_key]}"
        else:
            seen_keys[base_key] = 1
            final_key = base_key

        provisions.append(
            Provision(
                provision_key=final_key,
                article_number=art_num,
                clause_number=cl_num,
                point_label=pt_lbl,
                provision_heading=heading,
                citation_structure=cit_struct,  # type: ignore[arg-type]
                text="\n".join(body_lines),
            )
        )

    cur_key = "mo-dau"
    cur_art = ""
    cur_cl = ""
    cur_pt = ""
    cur_heading = "Mở đầu"
    cur_lines: list[str] = []
    in_quoted_amendment = False
    quoted_art = ""
    quoted_cl = ""

    current_parent_article_key = ""
    current_parent_clause_key = ""

    for line in lines:
        quoted_art_match = re.match(r"^[“\"']\s*Điều\s+(\d+)[\.\:]?\s*(.*)$", line)
        if quoted_art_match and current_parent_clause_key:
            add_provision(cur_key, cur_art, cur_cl, cur_pt, cur_heading, "parsed", cur_lines)
            in_quoted_amendment = True
            quoted_art = quoted_art_match.group(1)
            quoted_cl = ""
            cur_key = f"{current_parent_clause_key}/noi-dung-sua-doi/dieu-{quoted_art}"
            cur_art = quoted_art
            cur_cl = ""
            cur_pt = ""
            cur_heading = f"Điều {quoted_art} (nội dung sửa đổi)"
            cur_lines = [line]
            continue

        art_match = re.match(r"^Điều\s+(\d+)[\.\:]?\s*(.*)$", line)
        if art_match and not (in_quoted_amendment and line.startswith(("“", "\"", "'"))):
            add_provision(cur_key, cur_art, cur_cl, cur_pt, cur_heading, "parsed", cur_lines)
            in_quoted_amendment = False
            quoted_art = ""
            quoted_cl = ""
            art_num = art_match.group(1)
            heading_rest = art_match.group(2)
            cur_key = f"dieu-{art_num}"
            cur_art = art_num
            cur_cl = ""
            cur_pt = ""
            cur_heading = f"Điều {art_num}" + (f". {heading_rest}" if heading_rest else "")
            current_parent_article_key = f"dieu-{art_num}"
            current_parent_clause_key = ""
            cur_lines = [line]
            continue

        cl_match = re.match(r"^(\d+)\.\s+(.*)$", line)
        if cl_match:
            cl_num = cl_match.group(1)
            if in_quoted_amendment:
                add_provision(cur_key, cur_art, cur_cl, cur_pt, cur_heading, "parsed", cur_lines)
                quoted_cl = cl_num
                cur_key = f"{current_parent_clause_key}/noi-dung-sua-doi/dieu-{quoted_art}/khoan-{quoted_cl}"
                cur_art = quoted_art
                cur_cl = quoted_cl
                cur_pt = ""
                cur_heading = f"Khoản {quoted_cl} (nội dung sửa đổi)"
                cur_lines = [line]
                continue
            elif current_parent_article_key:
                add_provision(cur_key, cur_art, cur_cl, cur_pt, cur_heading, "parsed", cur_lines)
                cur_key = f"{current_parent_article_key}/khoan-{cl_num}"
                cur_art = cur_art
                cur_cl = cl_num
                cur_pt = ""
                cur_heading = f"Khoản {cl_num}"
                current_parent_clause_key = cur_key
                cur_lines = [line]
                continue

        pt_match = re.match(r"^([a-zđ])\)\s+(.*)$", line, re.IGNORECASE)
        if pt_match and (current_parent_clause_key or in_quoted_amendment):
            pt_lbl = pt_match.group(1).lower()
            add_provision(cur_key, cur_art, cur_cl, cur_pt, cur_heading, "parsed", cur_lines)
            if in_quoted_amendment:
                cur_key = f"{current_parent_clause_key}/noi-dung-sua-doi/dieu-{quoted_art}/khoan-{quoted_cl}/diem-{pt_lbl}"
            else:
                cur_key = f"{current_parent_clause_key}/diem-{pt_lbl}"
            cur_pt = pt_lbl
            cur_heading = f"Điểm {pt_lbl}"
            cur_lines = [line]
            continue

        cur_lines.append(line)

    add_provision(cur_key, cur_art, cur_cl, cur_pt, cur_heading, "parsed", cur_lines)
    return tuple(provisions)
