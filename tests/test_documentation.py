from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
CURRENT_DEVELOPMENT_DOCS = (
    "docs/architecture.md",
    "docs/development-workflow.md",
    "docs/legal-data-policy.md",
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
