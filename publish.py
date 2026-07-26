import argparse
import json
from pathlib import Path
import sys

from vbpl_kb.releases import ReleaseBuilder, ReleaseValidator, ReleaseManager


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish VBPL multi-resolution legal releases")
    parser.add_argument("--revision", type=str, default="rev-auto", help="Corpus revision string")
    parser.add_argument("--export-dir", type=str, default="data/exports", help="Export directory")
    args = parser.parse_args()

    export_dir = Path(args.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    print(f"Building candidate release for revision: {args.revision}...")
    builder = ReleaseBuilder(export_dir)
    manifest = builder.build_candidate(args.revision)

    print(f"Validating candidate release: {manifest.release_id}...")
    validator = ReleaseValidator(export_dir)
    report = validator.validate(manifest)

    if not report.is_valid:
        print(f"Validation FAILED for release {manifest.release_id}:", file=sys.stderr)
        for err in report.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"Promoting active release: {manifest.release_id}...")
    manager = ReleaseManager(export_dir)
    active = manager.promote(manifest)

    summary = {
        "status": "success",
        "release_id": active.release_id,
        "revision": args.revision,
        "manifest_sha256": active.manifest_sha256,
        "published_at": active.published_at,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
