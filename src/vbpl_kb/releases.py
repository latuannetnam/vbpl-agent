import os
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime, UTC
from typing import Any
from vbpl_kb.state import StateStore
from vbpl_kb.models import ReleaseManifest, ActiveRelease
from vbpl_kb.normalize import normalize_instrument
from vbpl_kb.publish import _get_doc_sig_from_title
from vbpl_kb.references import (
    extract_references,
    normalize_relationships,
    relationship_tokens,
    normalize_signature,
)


class ReleaseBlocked(Exception):
    pass


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _doc_filename(document_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", document_id).strip("_")
    return f"{cleaned}.json"


class ReleaseExporter:
    def __init__(self, store: StateStore, export_dir: Path):
        self.store = store
        self.export_dir = Path(export_dir)

    def load_manifest(self, release_id: str) -> ReleaseManifest:
        manifest_path = self.export_dir / "releases" / release_id / "manifest.json"
        if not manifest_path.exists():
            raise ReleaseBlocked(f"Manifest file missing for release {release_id}")
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            return ReleaseManifest(
                release_id=release_id,
                manifest_path=manifest_path.resolve(),
                manifest_sha256=_sha256_file(manifest_path),
                document_count=data.get("document_count", 0),
                section_count=data.get("section_count", 0),
                projection_schema_version=data.get("projection_schema_version", 2),
                published_at=data.get("published_at", ""),
                documents=data.get("documents", []),
            )
        except Exception as e:
            raise ReleaseBlocked(f"Failed to load manifest for {release_id}") from e

    def validate_candidate(self, manifest: ReleaseManifest) -> None:
        manifest_path = Path(manifest.manifest_path)
        if not manifest_path.exists():
            raise ReleaseBlocked("Manifest file missing; checksum validation failed")

        actual_sha256 = _sha256_file(manifest_path)
        if actual_sha256 != manifest.manifest_sha256:
            raise ReleaseBlocked("Manifest checksum mismatch")

        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ReleaseBlocked("Failed to parse manifest JSON; checksum invalid") from e

        version = manifest_data.get("projection_schema_version", 1)
        if version != 2:
            raise ReleaseBlocked(f"Unsupported projection schema version: {version}")

        manifest_dir = manifest_path.parent
        for doc_entry in manifest_data.get("documents", []):
            rel_path = doc_entry.get("relative_path", "")
            expected_sha256 = doc_entry.get("sha256", "")
            doc_file = manifest_dir / rel_path

            if not doc_file.exists():
                raise ReleaseBlocked(f"Document file missing: {rel_path}; checksum validation failed")

            # Path containment check
            try:
                doc_file.resolve().relative_to(manifest_dir.resolve())
            except ValueError:
                raise ReleaseBlocked(f"Document path escapes release directory: {rel_path}")

            if _sha256_file(doc_file) != expected_sha256:
                raise ReleaseBlocked(f"Document checksum mismatch for {rel_path}")

            try:
                doc_data = json.loads(doc_file.read_text(encoding="utf-8"))
            except Exception as e:
                raise ReleaseBlocked(f"Failed to parse document JSON for {rel_path}") from e

            doc_ver = doc_data.get("projection_schema_version")
            if doc_ver != 2:
                raise ReleaseBlocked(f"Unsupported projection schema version in document: {doc_ver}")

            doc_id = doc_data.get("document_id", "")
            if not isinstance(doc_id, str) or not doc_id.startswith("vbpl:"):
                raise ReleaseBlocked(f"Invalid document_id format: {doc_id}")

            sections = doc_data.get("sections")
            if not isinstance(sections, list) or not sections:
                raise ReleaseBlocked(f"Document {doc_id} has empty or invalid sections")

            seen_sections: set[str] = set()
            for sec in sections:
                if not isinstance(sec, dict):
                    raise ReleaseBlocked(f"Invalid section item in document {doc_id}")
                sec_id = sec.get("section_id")
                text = sec.get("text")
                link = sec.get("link")
                if not all(isinstance(v, str) and v for v in (sec_id, text, link)):
                    raise ReleaseBlocked(f"Invalid section fields in {doc_id}")
                sec_id_str = str(sec_id)
                if sec_id_str in seen_sections:
                    raise ReleaseBlocked(f"Duplicate section_id '{sec_id_str}' in document {doc_id}")
                seen_sections.add(sec_id_str)

            metadata = doc_data.get("metadata", {})
            if not isinstance(metadata, dict):
                raise ReleaseBlocked(f"Metadata in {doc_id} must be a dict")
            for k, v in metadata.items():
                if isinstance(v, list):
                    if not all(isinstance(item, str) for item in v):
                        raise ReleaseBlocked(f"Metadata list '{k}' in {doc_id} contains non-string item")
                elif not isinstance(v, str):
                    raise ReleaseBlocked(f"Metadata key '{k}' in {doc_id} is not string or list of strings")

    def write_candidate(self, run_id: str) -> ReleaseManifest:
        run = self.store.get_run(run_id)
        if not run:
            raise ReleaseBlocked(f"Crawl run {run_id} not found")
        if run.status != "completed" or run.coverage != 1.0:
            raise ReleaseBlocked(f"Crawl run is incomplete (status={run.status}, coverage={run.coverage})")

        cursor = self.store.conn.cursor()
        cursor.execute("SELECT vbpl_id, relative_path FROM raw_snapshots WHERE run_id = ?", (run_id,))
        snapshots = cursor.fetchall()

        manifest_path = self.export_dir / "releases" / run_id / "manifest.json"
        if manifest_path.exists():
            try:
                candidate = self.load_manifest(run_id)
                self.validate_candidate(candidate)
                print(f"Release candidate {run_id} already exists and validated; skipping re-export.", flush=True)
                return candidate
            except ReleaseBlocked:
                print(f"Existing candidate {run_id} failed validation; re-exporting...", flush=True)

        instrument_index: dict[str, str] = {}
        index_cursor = self.store.conn.cursor()
        index_cursor.execute(
            "SELECT DISTINCT s.vbpl_id, s.relative_path FROM raw_snapshots s "
            "JOIN status_observations o ON s.vbpl_id = o.vbpl_id "
            "WHERE s.endpoint = 'detail'"
        )
        for row in index_cursor.fetchall():
            vid = row["vbpl_id"]
            path = self.store.db_path.parent / row["relative_path"]
            if path.exists():
                try:
                    raw_data = json.loads(path.read_text(encoding="utf-8"))["data"]
                    signature_text = raw_data.get("docNum", "")
                    sig_info = _get_doc_sig_from_title(
                        f"{raw_data.get('title', '')} {signature_text}"
                    )
                    if sig_info:
                        dtype, dnum = sig_info
                        sig = normalize_signature(dtype, dnum)
                        instrument_index[sig] = vid
                except Exception:
                    pass

        release_docs_dir = self.export_dir / "releases" / run_id / "documents"
        release_docs_dir.mkdir(parents=True, exist_ok=True)

        doc_entries: list[dict[str, Any]] = []
        total_snaps = len(snapshots)
        total_section_count = 0

        for idx, snap in enumerate(snapshots, start=1):
            vbpl_id = snap["vbpl_id"]
            snap_path = self.store.db_path.parent / snap["relative_path"]
            if not snap_path.exists():
                raise ReleaseBlocked(f"Snapshot file not found: {snap_path}")

            try:
                raw_data = json.loads(snap_path.read_text(encoding="utf-8"))["data"]
            except Exception as e:
                raise ReleaseBlocked(f"Failed to parse snapshot JSON for ID {vbpl_id}") from e

            status_obs = self.store.latest_status(vbpl_id)
            if not status_obs:
                raise ReleaseBlocked(f"Missing status observation for ID {vbpl_id}")

            full_text = raw_data.get("fullText") or ""
            candidates = extract_references(vbpl_id, "whole", full_text)
            structured_raw = raw_data.get("references") or []
            edges = normalize_relationships(
                from_vbpl_id=vbpl_id,
                structured=structured_raw,
                candidates=candidates,
                instrument_index=instrument_index,
                corpus_revision=run_id,
            )

            for edge in edges:
                self.store.record_reference(run_id, edge)

            tokens = relationship_tokens(edges)
            final_doc = normalize_instrument(raw_data, status_obs, run_id, tokens)
            total_section_count += len(final_doc.sections)

            doc_payload = {
                "projection_schema_version": final_doc.projection_schema_version,
                "document_id": final_doc.document_id,
                "sections": [sec.model_dump() for sec in final_doc.sections],
                "link": final_doc.link,
                "metadata": final_doc.metadata,
            }

            filename = _doc_filename(final_doc.document_id)
            doc_path = release_docs_dir / filename

            json_text = json.dumps(doc_payload, ensure_ascii=False, indent=2)
            doc_bytes = json_text.encode("utf-8")
            doc_sha256 = hashlib.sha256(doc_bytes).hexdigest()

            temp_path = doc_path.with_suffix(".tmp")
            temp_path.write_bytes(doc_bytes)
            temp_path.replace(doc_path)

            doc_entries.append({
                "document_id": final_doc.document_id,
                "relative_path": f"documents/{filename}",
                "sha256": doc_sha256,
                "updated_at": status_obs.checked_at.isoformat(),
            })

            if idx % 1000 == 0 or idx == total_snaps:
                print(f"export: written {idx}/{total_snaps} release documents...", flush=True)

        published_at = datetime.now(UTC).isoformat()
        manifest_payload = {
            "release_id": run_id,
            "projection_schema_version": 2,
            "document_count": len(doc_entries),
            "section_count": total_section_count,
            "published_at": published_at,
            "documents": doc_entries,
        }

        _write_json_atomically(manifest_path, manifest_payload)
        manifest_sha256 = _sha256_file(manifest_path)

        self.store.record_release_run(
            run_id=run_id,
            status="candidate",
            manifest_path=str(manifest_path.resolve()),
            manifest_sha256=manifest_sha256,
            document_count=len(doc_entries),
        )

        return ReleaseManifest(
            release_id=run_id,
            manifest_path=manifest_path.resolve(),
            manifest_sha256=manifest_sha256,
            document_count=len(doc_entries),
            section_count=total_section_count,
            projection_schema_version=2,
            published_at=published_at,
            documents=doc_entries,
        )

    def promote(self, manifest: ReleaseManifest) -> ActiveRelease:
        try:
            self.validate_candidate(manifest)
        except Exception as e:
            self.store.record_release_run(manifest.release_id, "blocked")
            if isinstance(e, ReleaseBlocked):
                raise
            raise ReleaseBlocked(f"Validation failed: {e}") from e

        manifest_path = Path(manifest.manifest_path)
        published_at = datetime.now(UTC).isoformat()
        active_pointer_path = self.export_dir / "active-release.json"
        active_payload = {
            "release_id": manifest.release_id,
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": manifest.manifest_sha256,
            "published_at": published_at,
        }
        _write_json_atomically(active_pointer_path, active_payload)

        self.store.record_release_run(
            run_id=manifest.release_id,
            status="active",
            manifest_path=str(manifest_path.resolve()),
            manifest_sha256=manifest.manifest_sha256,
            document_count=manifest.document_count,
        )
        self.store.set_active_run(manifest.release_id)

        return ActiveRelease(
            release_id=manifest.release_id,
            manifest_path=str(manifest_path.resolve()),
            manifest_sha256=manifest.manifest_sha256,
            published_at=published_at,
        )

    def read_active(self) -> ActiveRelease | None:
        active_pointer_path = self.export_dir / "active-release.json"
        if not active_pointer_path.exists():
            return None
        try:
            payload = json.loads(active_pointer_path.read_text(encoding="utf-8"))
            return ActiveRelease(
                release_id=payload["release_id"],
                manifest_path=payload["manifest_path"],
                manifest_sha256=payload["manifest_sha256"],
                published_at=payload["published_at"],
            )
        except Exception:
            return None
