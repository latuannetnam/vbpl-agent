import os
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime, UTC
from typing import Any
from vbpl_kb.state import StateStore
from vbpl_kb.models import ReleaseManifest, ActiveRelease
from vbpl_kb.publish import build_projection, _get_doc_sig_from_title
from vbpl_kb.references import (
    extract_references,
    resolve_reference,
    extract_structured_references,
    normalize_signature
)


class ReleaseBlocked(Exception):
    pass


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


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

    def write_candidate(self, run_id: str) -> ReleaseManifest:
        run = self.store.get_run(run_id)
        if not run:
            raise ReleaseBlocked(f"Crawl run {run_id} not found")
        if run.status != "completed" or run.coverage != 1.0:
            raise ReleaseBlocked(f"Crawl run is incomplete (status={run.status}, coverage={run.coverage})")

        cursor = self.store.conn.cursor()
        cursor.execute("SELECT vbpl_id, relative_path FROM raw_snapshots WHERE run_id = ?", (run_id,))
        snapshots = cursor.fetchall()

        # Build instrument index
        instrument_index: dict[str, str] = {}
        index_cursor = self.store.conn.cursor()
        index_cursor.execute("SELECT vbpl_id FROM status_observations")
        for row in index_cursor.fetchall():
            vid = row["vbpl_id"]
            detail_cursor = self.store.conn.cursor()
            detail_cursor.execute(
                "SELECT relative_path FROM raw_snapshots WHERE vbpl_id = ? AND endpoint = 'detail' LIMIT 1",
                (vid,)
            )
            detail_snap = detail_cursor.fetchone()
            if detail_snap:
                path = self.store.db_path.parent / detail_snap["relative_path"]
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

        for snap in snapshots:
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

            doc = build_projection(raw_data, status_obs, run_id)
            candidates = extract_references(vbpl_id, "whole", doc.content)
            resolved_edges = extract_structured_references(vbpl_id, raw_data)
            for cand in candidates:
                edge = resolve_reference(cand, instrument_index)
                resolved_edges.append(edge)
            for edge in resolved_edges:
                self.store.record_reference(run_id, edge)

            final_doc = build_projection(raw_data, status_obs, run_id, resolved_edges, self.store)

            doc_payload = {
                "document_id": final_doc.document_id,
                "content": final_doc.content,
                "link": final_doc.link,
                "metadata": final_doc.metadata
            }

            filename = _doc_filename(final_doc.document_id)
            doc_path = release_docs_dir / filename
            _write_json_atomically(doc_path, doc_payload)

            doc_sha256 = _sha256_file(doc_path)
            doc_entries.append({
                "document_id": final_doc.document_id,
                "relative_path": f"documents/{filename}",
                "sha256": doc_sha256,
                "updated_at": status_obs.checked_at.isoformat()
            })

        published_at = datetime.now(UTC).isoformat()
        manifest_path = self.export_dir / "releases" / run_id / "manifest.json"
        manifest_payload = {
            "release_id": run_id,
            "document_count": len(doc_entries),
            "published_at": published_at,
            "documents": doc_entries
        }

        _write_json_atomically(manifest_path, manifest_payload)
        manifest_sha256 = _sha256_file(manifest_path)

        self.store.record_release_run(
            run_id=run_id,
            status="candidate",
            manifest_path=str(manifest_path.resolve()),
            manifest_sha256=manifest_sha256,
            document_count=len(doc_entries)
        )

        return ReleaseManifest(
            release_id=run_id,
            manifest_path=manifest_path.resolve(),
            manifest_sha256=manifest_sha256,
            document_count=len(doc_entries),
            published_at=published_at,
            documents=doc_entries
        )

    def promote(self, manifest: ReleaseManifest) -> ActiveRelease:
        manifest_path = Path(manifest.manifest_path)
        if not manifest_path.exists():
            self.store.record_release_run(manifest.release_id, "blocked")
            raise ReleaseBlocked("Manifest file missing; checksum validation failed")

        actual_sha256 = _sha256_file(manifest_path)
        if actual_sha256 != manifest.manifest_sha256:
            self.store.record_release_run(manifest.release_id, "blocked")
            raise ReleaseBlocked("Manifest checksum mismatch")

        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            self.store.record_release_run(manifest.release_id, "blocked")
            raise ReleaseBlocked("Failed to parse manifest JSON; checksum invalid") from e

        manifest_dir = manifest_path.parent
        for doc_entry in manifest_data.get("documents", []):
            rel_path = doc_entry.get("relative_path", "")
            expected_sha256 = doc_entry.get("sha256", "")
            doc_file = manifest_dir / rel_path

            if not doc_file.exists():
                self.store.record_release_run(manifest.release_id, "blocked")
                raise ReleaseBlocked(f"Document file missing: {rel_path}; checksum validation failed")

            if _sha256_file(doc_file) != expected_sha256:
                self.store.record_release_run(manifest.release_id, "blocked")
                raise ReleaseBlocked(f"Document checksum mismatch for {rel_path}")

        published_at = datetime.now(UTC).isoformat()
        active_pointer_path = self.export_dir / "active-release.json"
        active_payload = {
            "release_id": manifest.release_id,
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": manifest.manifest_sha256,
            "published_at": published_at
        }
        _write_json_atomically(active_pointer_path, active_payload)

        self.store.record_release_run(
            run_id=manifest.release_id,
            status="active",
            manifest_path=str(manifest_path.resolve()),
            manifest_sha256=manifest.manifest_sha256,
            document_count=manifest.document_count
        )
        self.store.set_active_run(manifest.release_id)

        return ActiveRelease(
            release_id=manifest.release_id,
            manifest_path=str(manifest_path.resolve()),
            manifest_sha256=manifest.manifest_sha256,
            published_at=published_at
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
                published_at=payload["published_at"]
            )
        except Exception:
            return None
