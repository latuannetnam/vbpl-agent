import json
import re
from collections.abc import Callable
from vbpl_kb.state import StateStore
from vbpl_kb.onyx import OnyxIngestionClient
from vbpl_kb.models import OnyxDocument
from vbpl_kb.normalize import normalize_instrument
from vbpl_kb.references import (
    extract_references,
    resolve_reference,
    append_related_documents_section,
    extract_structured_references,
    normalize_signature
)

class PublishBlocked(Exception):
    pass

class PublishSummary:
    def __init__(self, upserted_count: int, deleted_count: int, run_id: str):
        self.upserted_count = upserted_count
        self.deleted_count = deleted_count
        self.run_id = run_id


ProgressReporter = Callable[[str], None]

def _get_doc_sig_from_title(title: str) -> tuple[str, str] | None:
    doc_types = ["Nghị định", "Luật", "Thông tư", "Quyết định", "Nghị quyết", "Hiến pháp", "Sắc lệnh", "Pháp lệnh", "Chỉ thị"]
    doc_types_regex = "|".join(doc_types)
    pattern = re.compile(
        r"\b(" + doc_types_regex + r")\s+(?:số\s+)?([0-9]+[\w\-\/\.]*)",
        re.IGNORECASE
    )
    m = pattern.search(title)
    if m:
        return m.group(1), m.group(2).rstrip(".,)")
    return None

class Publisher:
    def __init__(
        self,
        store: StateStore,
        onyx: OnyxIngestionClient,
        progress: ProgressReporter | None = None,
    ):
        self.store = store
        self.onyx = onyx
        self.progress = progress

    def _report(self, message: str) -> None:
        if self.progress is not None:
            self.progress(message)

    def publish(self, run_id: str) -> PublishSummary:
        # Load run
        run = self.store.get_run(run_id)
        if not run:
            raise PublishBlocked(f"Crawl run {run_id} not found")
        if run.status != "completed" or run.coverage != 1.0:
            raise PublishBlocked(f"crawl run is not complete (status={run.status}, coverage={run.coverage})")

        # Query all snapshots for this run
        cursor = self.store.conn.cursor()
        cursor.execute("SELECT vbpl_id, relative_path FROM raw_snapshots WHERE run_id = ?", (run_id,))
        snapshots = cursor.fetchall()
        self._report(f"publish: preparing {len(snapshots)} documents")
        
        # Build instrument index from all known status observations
        instrument_index: dict[str, str] = {}
        index_cursor = self.store.conn.cursor()
        index_cursor.execute("SELECT vbpl_id FROM status_observations")
        for row in index_cursor.fetchall():
            vid = row["vbpl_id"]
            # get details
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

        # Normalize and upsert each document
        upserted_count = 0
        current_doc_ids: set[str] = set()
        
        for snap in snapshots:
            vbpl_id = snap["vbpl_id"]
            path = self.store.db_path.parent / snap["relative_path"]
            if not path.exists():
                raise PublishBlocked(f"Snapshot file not found: {path}")
                
            try:
                raw_data = json.loads(path.read_text(encoding="utf-8"))["data"]
            except Exception as e:
                raise PublishBlocked(f"Failed to parse snapshot JSON for ID {vbpl_id}") from e
                
            status_obs = self.store.latest_status(vbpl_id)
            if not status_obs:
                raise PublishBlocked(f"Missing status observation for ID {vbpl_id}")
                
            # Perform initial normalization
            doc = normalize_instrument(raw_data, status_obs, run_id)
            
            # Extract and resolve cross references
            candidates = extract_references(vbpl_id, "whole", doc.content)
            resolved_edges = extract_structured_references(vbpl_id, raw_data)
            for cand in candidates:
                edge = resolve_reference(cand, instrument_index)
                resolved_edges.append(edge)
            for edge in resolved_edges:
                self.store.record_reference(run_id, edge)
                
            # Append resolved references block
            final_content = append_related_documents_section(doc.content, resolved_edges, self.store)
            
            final_doc = OnyxDocument(
                document_id=doc.document_id,
                content=final_content,
                link=doc.link,
                metadata=doc.metadata
            )
            
            # Upsert to Onyx
            self.onyx.upsert(final_doc)
            
            # Save projection in DB
            with self.store.conn:
                self.store.conn.execute("""
                    INSERT OR REPLACE INTO onyx_projection (document_id, content, link, metadata_json, run_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (final_doc.document_id, final_doc.content, final_doc.link, json.dumps(final_doc.metadata), run_id))
                
            current_doc_ids.add(final_doc.document_id)
            upserted_count += 1
            if upserted_count % 100 == 0:
                self._report(f"publish: upserted {upserted_count}/{len(snapshots)} documents")

        self._report(f"publish: upserted {upserted_count}/{len(snapshots)} documents")

        # Deletion logic: documents that were active but are not in the current run
        deleted_count = 0
        prior_run_id = self.store.get_active_run_id()
        if prior_run_id and prior_run_id != run_id:
            del_cursor = self.store.conn.cursor()
            del_cursor.execute("SELECT document_id FROM onyx_projection WHERE run_id = ?", (prior_run_id,))
            prior_doc_ids = {r["document_id"] for r in del_cursor.fetchall()}
            
            to_delete = prior_doc_ids - current_doc_ids
            for doc_id in to_delete:
                self.onyx.delete(doc_id)
                deleted_count += 1
                if deleted_count % 100 == 0:
                    self._report(f"publish: deleted {deleted_count}/{len(to_delete)} stale documents")
            if to_delete:
                self._report(f"publish: deleted {deleted_count}/{len(to_delete)} stale documents")

        # Mark the revision active
        self.store.set_active_run(run_id)
        self._report(
            f"publish: completed; upserted={upserted_count} deleted={deleted_count}"
        )

        return PublishSummary(
            upserted_count=upserted_count,
            deleted_count=deleted_count,
            run_id=run_id
        )
