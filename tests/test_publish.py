from pathlib import Path
from vbpl_kb.releases import ReleaseBuilder, ReleaseValidator, ReleaseManager


def test_publish_builder_and_promotion(tmp_path: Path) -> None:
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    builder = ReleaseBuilder(export_dir)
    manifest = builder.build_candidate("rev-publish-test")

    validator = ReleaseValidator(export_dir)
    report = validator.validate(manifest)
    assert report.is_valid is True

    manager = ReleaseManager(export_dir)
    active = manager.promote(manifest)
    assert active.release_id == manifest.release_id
