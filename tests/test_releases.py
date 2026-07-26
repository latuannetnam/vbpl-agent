import json
from pathlib import Path
import pytest
from datetime import datetime, timezone

from vbpl_kb.models import ActiveRelease, ReleaseManifest
from vbpl_kb.releases import (
    ReleaseBuilder,
    ReleaseValidator,
    ReleaseManager,
    ValidationReport,
)


def test_candidate_write_and_promotion_success(tmp_path: Path) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    builder = ReleaseBuilder(export_dir)
    manifest = builder.build_candidate(
        revision="rev-2026-07-26",
        sample_documents={
            "current": [
                {"document_id": "vbpl:101:current:article:dieu-01", "sections": [{"section_id": "s1", "text": "Text 1", "link": "http://x"}], "link": "http://x", "metadata": {}}
            ],
            "history": [],
            "evidence": [],
        },
    )
    assert manifest.release_id.startswith("release-rev-2026-07-26")
    assert manifest.document_count == 1

    validator = ReleaseValidator(export_dir)
    report = validator.validate(manifest)
    assert report.is_valid is True

    manager = ReleaseManager(export_dir)
    active = manager.promote(manifest)
    assert active.release_id == manifest.release_id
    assert (export_dir / "active-release.json").exists()


def test_invalid_candidate_blocks_promotion(tmp_path: Path) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    invalid_manifest = ReleaseManifest(
        release_id="non-existent-release",
        manifest_path=export_dir / "missing" / "manifest.json",
        manifest_sha256="badhash",
        document_count=0,
        section_count=0,
        projection_schema_version=2,
    )

    manager = ReleaseManager(export_dir)
    with pytest.raises(ValueError, match="Cannot promote invalid release"):
        manager.promote(invalid_manifest)

    assert not (export_dir / "active-release.json").exists()
