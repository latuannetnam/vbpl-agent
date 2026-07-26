from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from vbpl_kb.models import ActiveRelease, ReleaseManifest


@dataclass(frozen=True)
class ValidationReport:
    release_id: str
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    checked_at: datetime


class ReleaseBuilder:
    def __init__(self, export_dir: Any = None, *args: Any, **kwargs: Any) -> None:
        self.export_dir = Path(export_dir) if export_dir is not None else Path("data/exports")

    def build_candidate(
        self,
        revision: str,
        sample_documents: Mapping[str, Sequence[Any]] | None = None,
    ) -> ReleaseManifest:
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        release_id = f"release-{revision}-{timestamp_str}"
        release_dir = self.export_dir / "releases" / release_id
        release_dir.mkdir(parents=True, exist_ok=True)

        views_meta: dict[str, dict[str, Any]] = {}
        sample_documents = sample_documents or {"current": [], "history": [], "evidence": []}

        for view in ("current", "history", "evidence"):
            view_dir = release_dir / view
            view_dir.mkdir(exist_ok=True)

            docs = sample_documents.get(view, [])
            docs_file = view_dir / "documents-00000.jsonl"
            active_file = view_dir / "active-ids.jsonl"
            delta_file = view_dir / "delta-00000.jsonl"

            active_ids: list[str] = []
            with open(docs_file, "w", encoding="utf-8") as f_docs, open(delta_file, "w", encoding="utf-8") as f_delta:
                for doc_obj in docs:
                    if hasattr(doc_obj, "to_dict"):
                        doc_dict = doc_obj.to_dict()
                    elif isinstance(doc_obj, dict):
                        doc_dict = doc_obj
                    else:
                        raise TypeError(f"Unsupported document object type: {type(doc_obj)}")

                    doc_str = json.dumps(doc_dict, ensure_ascii=False)
                    f_docs.write(doc_str + "\n")
                    f_delta.write(doc_str + "\n")

                    d_id = doc_dict.get("document_id") or doc_dict.get("id")
                    if d_id:
                        active_ids.append(str(d_id))

            with open(active_file, "w", encoding="utf-8") as f_act:
                for a_id in active_ids:
                    f_act.write(a_id + "\n")

            act_bytes = active_file.read_bytes()
            act_hash = hashlib.sha256(act_bytes).hexdigest()

            views_meta[view] = {
                "document_count": len(docs),
                "shard_count": 1,
                "active_ids_hash": act_hash,
            }

        manifest_data = {
            "release_id": release_id,
            "revision": revision,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "projection_schema_version": 2,
            "views": views_meta,
        }

        manifest_path = release_dir / "manifest.json"
        manifest_bytes = json.dumps(manifest_data, indent=2, ensure_ascii=False).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()

        return ReleaseManifest(
            release_id=release_id,
            manifest_path=manifest_path,
            manifest_sha256=manifest_hash,
            document_count=sum(v["document_count"] for v in views_meta.values()),
            section_count=sum(v["document_count"] for v in views_meta.values()),
            projection_schema_version=2,
            published_at=datetime.now(timezone.utc).isoformat(),
        )

    def write_candidate(self, revision: str) -> ReleaseManifest:
        return self.build_candidate(revision)

    def promote(self, candidate: ReleaseManifest) -> ActiveRelease:
        return ReleaseManager(self.export_dir).promote(candidate)

    def read_active(self) -> ActiveRelease | None:
        return ReleaseManager(self.export_dir).read_active()

    def load_manifest(self, release_id: str) -> ReleaseManifest:
        manifest_path = self.export_dir / "releases" / release_id / "manifest.json"
        if not manifest_path.exists():
            raise ValueError(f"Manifest not found: {manifest_path}")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return ReleaseManifest(
            release_id=data["release_id"],
            manifest_path=manifest_path,
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            document_count=sum(v.get("document_count", 0) for v in data.get("views", {}).values()),
            section_count=sum(v.get("document_count", 0) for v in data.get("views", {}).values()),
            projection_schema_version=data.get("projection_schema_version", 2),
            published_at=data.get("created_at", ""),
        )

    def validate_candidate(self, candidate: ReleaseManifest) -> ValidationReport:
        return ReleaseValidator(self.export_dir).validate(candidate)


ReleaseExporter = ReleaseBuilder
ReleaseBlocked = ValueError


class ReleaseValidator:
    def __init__(self, export_dir: Path | str) -> None:
        self.export_dir = Path(export_dir)

    def validate(self, manifest: ReleaseManifest) -> ValidationReport:
        release_dir = self.export_dir / "releases" / manifest.release_id
        errors: list[str] = []
        warnings: list[str] = []

        if not release_dir.exists():
            errors.append(f"Release directory not found: {release_dir}")

        manifest_file = release_dir / "manifest.json"
        if not manifest_file.exists():
            errors.append("manifest.json not found")
        else:
            calc_hash = hashlib.sha256(manifest_file.read_bytes()).hexdigest()
            if calc_hash != manifest.manifest_sha256:
                errors.append(f"Manifest SHA256 mismatch: {calc_hash} != {manifest.manifest_sha256}")

        for view in ("current", "history", "evidence"):
            view_dir = release_dir / view
            if not view_dir.exists():
                errors.append(f"View directory missing: {view}")

        val_report = ValidationReport(
            release_id=manifest.release_id,
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            checked_at=datetime.now(timezone.utc),
        )

        if release_dir.exists():
            val_file = release_dir / "validation.json"
            val_data = {
                "release_id": val_report.release_id,
                "is_valid": val_report.is_valid,
                "errors": val_report.errors,
                "warnings": val_report.warnings,
                "checked_at": val_report.checked_at.isoformat(),
            }
            val_file.write_text(json.dumps(val_data, indent=2, ensure_ascii=False), encoding="utf-8")

        return val_report


class ReleaseManager:
    def __init__(self, export_dir: Path | str) -> None:
        self.export_dir = Path(export_dir)

    def promote(self, manifest: ReleaseManifest) -> ActiveRelease:
        validator = ReleaseValidator(self.export_dir)
        report = validator.validate(manifest)
        if not report.is_valid:
            raise ValueError(f"Cannot promote invalid release: {report.errors}")

        active = ActiveRelease(
            release_id=manifest.release_id,
            manifest_path=str(manifest.manifest_path),
            manifest_sha256=manifest.manifest_sha256,
            published_at=datetime.now(timezone.utc).isoformat(),
        )

        active_file = self.export_dir / "active-release.json"
        active_json = json.dumps(
            {
                "release_id": active.release_id,
                "manifest_path": active.manifest_path,
                "manifest_sha256": active.manifest_sha256,
                "published_at": active.published_at,
            },
            indent=2,
            ensure_ascii=False,
        ).encode("utf-8")

        with tempfile.NamedTemporaryFile("wb", dir=self.export_dir, delete=False) as tmp_f:
            tmp_f.write(active_json)
            tmp_f.flush()
            os.fsync(tmp_f.fileno())
            tmp_name = tmp_f.name

        os.replace(tmp_name, active_file)
        return active

    def read_active(self) -> ActiveRelease | None:
        active_file = self.export_dir / "active-release.json"
        if not active_file.exists():
            return None
        data = json.loads(active_file.read_text(encoding="utf-8"))
        return ActiveRelease(
            release_id=data["release_id"],
            manifest_path=data["manifest_path"],
            manifest_sha256=data["manifest_sha256"],
            published_at=data["published_at"],
        )
