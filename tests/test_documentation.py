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
