from pathlib import Path
import pytest

ROOT = Path(__file__).parents[1]
CURRENT_DEVELOPMENT_DOCS = (
    "docs/architecture.md",
    "docs/development-workflow.md",
    "docs/legal-data-policy.md",
    "docs/operations.md",
    "docs/onyx-agent-setup.md",
)
AUTHORITY_FIELDS = (
    "**Status:** Current",
    "**Applies to:**",
    "**Use for:**",
    "**Do not use for:**",
)


@pytest.mark.parametrize("relative_path", CURRENT_DEVELOPMENT_DOCS)
def test_current_development_documents_have_authority_blocks(
    relative_path: str,
) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")

    for field in AUTHORITY_FIELDS:
        assert field in text, f"{relative_path} is missing {field}"


ENTRYPOINTS = ("AGENTS.md", "README.md")
CURRENT_DOCUMENT_LINKS = (
    "docs/architecture.md",
    "docs/development-workflow.md",
    "docs/legal-data-policy.md",
    "docs/operations.md",
    "docs/onyx-agent-setup.md",
)


@pytest.mark.parametrize("relative_path", ENTRYPOINTS)
def test_entrypoints_have_authority_blocks(relative_path: str) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")

    for field in AUTHORITY_FIELDS:
        assert field in text, f"{relative_path} is missing {field}"


@pytest.mark.parametrize("relative_path", ENTRYPOINTS)
def test_entrypoints_link_only_to_current_documents(relative_path: str) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")

    for document in CURRENT_DOCUMENT_LINKS:
        assert document in text, f"{relative_path} is missing {document}"
    assert "docs/superpowers/specs/" not in text
    assert "docs/superpowers/plans/" not in text


@pytest.mark.parametrize(
    "relative_path",
    ("docs/operations.md", "docs/onyx-agent-setup.md"),
)
def test_runbooks_do_not_link_to_dated_design_specs(relative_path: str) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")

    assert "docs/superpowers/specs/" not in text
    assert "superpowers/specs/" not in text


def test_canonical_agent_instruction_requires_staged_authority_bundle_search() -> None:
    text = (ROOT / "docs/onyx-agent-instruction.md").read_text(encoding="utf-8")
    required = (
        "internal_search",
        "vbpl_export",
        "phiên bản phát hành mới nhất",
        "xác định tọa độ pháp lý",
        "truy xuất quy định điều chỉnh trực tiếp",
        "mở rộng authority bundle",
        "relation_tokens",
        "cùng một cơ quan có thẩm quyền",
        "01/07/2025",
        "28/02/2027",
        "Không tìm thấy căn cứ VBPL đã được xác minh để trả lời câu hỏi này.",
    )
    for phrase in required:
        assert phrase in text, f"Missing phrase: {phrase}"
    assert "Hiến pháp > Luật > Nghị định > Thông tư" not in text


def test_current_docs_route_hierarchy_work_without_historical_links() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "hierarchy" in agents.casefold()
    assert "docs/legal-data-policy.md" in agents
    assert "docs/architecture.md" in agents
    assert "docs/superpowers/specs/" not in agents
    assert "docs/superpowers/plans/" not in agents
