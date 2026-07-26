from pathlib import Path

from vbpl_kb.releases import (
    ReleaseBuilder,
    ReleaseValidator,
    ReleaseManager,
)


def test_sharded_release_directory_structure(tmp_path: Path) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    builder = ReleaseBuilder(export_dir=export_dir)
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

    release_dir = export_dir / "releases" / manifest.release_id
    assert release_dir.exists()
    assert (release_dir / "manifest.json").exists()

    assert (release_dir / "current" / "documents-00000.jsonl").exists()
    assert (release_dir / "current" / "active-ids.jsonl").exists()

    assert (release_dir / "history" / "documents-00000.jsonl").exists()
    assert (release_dir / "history" / "active-ids.jsonl").exists()

    assert (release_dir / "evidence" / "documents-00000.jsonl").exists()
    assert (release_dir / "evidence" / "active-ids.jsonl").exists()


def test_validation_and_atomic_promotion(tmp_path: Path) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    builder = ReleaseBuilder(export_dir=export_dir)
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

    validator = ReleaseValidator(export_dir=export_dir)
    report = validator.validate(manifest)
    assert report.is_valid is True

    manager = ReleaseManager(export_dir=export_dir)
    active = manager.promote(manifest)

    assert active.release_id == manifest.release_id
    assert (export_dir / "active-release.json").exists()
