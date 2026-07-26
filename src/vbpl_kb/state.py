import sqlite3
import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any
from vbpl_kb.models import StatusObservation, CrawlRun, CatalogEntry, DeltaManifest

class StateStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    @classmethod
    def open(cls, db_path: Path) -> "StateStore":
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return cls(db_path)

    def close(self) -> None:
        self.conn.close()

    def _init_db(self) -> None:
        with self.conn:
            # crawl_runs
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS crawl_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    coverage REAL NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT
                )
            """)
            # raw_snapshots
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_snapshots (
                    run_id TEXT NOT NULL,
                    vbpl_id TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    PRIMARY KEY (run_id, vbpl_id, endpoint)
                )
            """)
            # status_observations
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS status_observations (
                    vbpl_id TEXT NOT NULL,
                    eff_status TEXT NOT NULL,
                    eff_from TEXT,
                    checked_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    PRIMARY KEY (vbpl_id, run_id),
                    FOREIGN KEY (run_id) REFERENCES crawl_runs(run_id)
                )
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status_obs_checked
                ON status_observations (vbpl_id, checked_at DESC)
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS crawl_catalog_entries (
                    run_id TEXT NOT NULL,
                    vbpl_id TEXT NOT NULL,
                    catalog_page INTEGER NOT NULL,
                    PRIMARY KEY (run_id, vbpl_id),
                    FOREIGN KEY (run_id) REFERENCES crawl_runs(run_id)
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS crawl_checkpoints (
                    run_id TEXT PRIMARY KEY,
                    next_catalog_page INTEGER NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES crawl_runs(run_id)
                )
            """)
            # legal_references
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_references (
                    run_id TEXT,
                    from_vbpl_id TEXT NOT NULL,
                    from_provision_key TEXT NOT NULL,
                    to_vbpl_id TEXT,
                    to_provision_key TEXT,
                    relation_type TEXT NOT NULL,
                    source_quote TEXT NOT NULL
                )
            """)
            reference_columns = {
                row["name"]
                for row in self.conn.execute("PRAGMA table_info(legal_references)")
            }
            if "run_id" not in reference_columns:
                self.conn.execute("ALTER TABLE legal_references ADD COLUMN run_id TEXT")
            if "evidence_kind" not in reference_columns:
                self.conn.execute("ALTER TABLE legal_references ADD COLUMN evidence_kind TEXT NOT NULL DEFAULT 'text_candidate'")
            if "evidence_reference" not in reference_columns:
                self.conn.execute("ALTER TABLE legal_references ADD COLUMN evidence_reference TEXT NOT NULL DEFAULT ''")
            if "source_offset" not in reference_columns:
                self.conn.execute("ALTER TABLE legal_references ADD COLUMN source_offset INTEGER")
            if "resolution_state" not in reference_columns:
                self.conn.execute("ALTER TABLE legal_references ADD COLUMN resolution_state TEXT NOT NULL DEFAULT 'unresolved'")
            if "evidence_hash" not in reference_columns:
                self.conn.execute("ALTER TABLE legal_references ADD COLUMN evidence_hash TEXT NOT NULL DEFAULT ''")
            if "corpus_revision" not in reference_columns:
                self.conn.execute("ALTER TABLE legal_references ADD COLUMN corpus_revision TEXT NOT NULL DEFAULT ''")
            if "searchable" not in reference_columns:
                self.conn.execute("ALTER TABLE legal_references ADD COLUMN searchable INTEGER NOT NULL DEFAULT 0")

            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_legal_ref_from
                ON legal_references (from_vbpl_id, from_provision_key)
            """)
            # onyx_projection
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS onyx_projection (
                    document_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    link TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES crawl_runs(run_id)
                )
            """)
            # active_revision
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS active_revision (
                    run_id TEXT PRIMARY KEY,
                    activated_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES crawl_runs(run_id)
                )
            """)
            # release_runs
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS release_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    manifest_path TEXT,
                    manifest_sha256 TEXT,
                    document_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES crawl_runs(run_id)
                )
            """)

            # catalog_scans
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS catalog_scans (
                    run_id TEXT PRIMARY KEY,
                    complete INTEGER NOT NULL,
                    item_count INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    FOREIGN KEY (run_id) REFERENCES crawl_runs(run_id)
                )
            """)

            # catalog_entries
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS catalog_entries (
                    run_id TEXT NOT NULL,
                    vbpl_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    title TEXT NOT NULL,
                    doc_num TEXT,
                    doc_type TEXT,
                    updated_date TEXT,
                    eff_status TEXT,
                    eff_to TEXT,
                    raw_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, vbpl_id),
                    FOREIGN KEY (run_id) REFERENCES catalog_scans(run_id)
                )
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_catalog_entries_run
                ON catalog_entries (run_id)
            """)

            # catalog_removals
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS catalog_removals (
                    vbpl_id TEXT PRIMARY KEY,
                    absence_count INTEGER NOT NULL DEFAULT 1,
                    first_absent_run_id TEXT NOT NULL,
                    last_absent_run_id TEXT NOT NULL,
                    status TEXT NOT NULL
                )
            """)

            # document_versions
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS document_versions (
                    vbpl_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (vbpl_id, version_id),
                    FOREIGN KEY (run_id) REFERENCES crawl_runs(run_id)
                )
            """)

            # delta_batches
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS delta_batches (
                    batch_id TEXT PRIMARY KEY,
                    release_id TEXT NOT NULL,
                    parent_release_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    upsert_ids_json TEXT NOT NULL,
                    tombstone_ids_json TEXT NOT NULL,
                    manifest_path TEXT NOT NULL,
                    checksum_sha256 TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    acknowledged_at TEXT
                )
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_delta_batches_created
                ON delta_batches (created_at)
            """)


    def begin_run(self, run_id: str) -> str:
        started_at = datetime.now(UTC).isoformat()
        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO crawl_runs (run_id, status, coverage, started_at, finished_at)
                VALUES (?, ?, ?, ?, NULL)
            """, (run_id, "running", 0.0, started_at))
        return run_id

    def record_snapshot(self, run_id: str, vbpl_id: str, endpoint: str, content: str, content_hash: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT 1 FROM raw_snapshots WHERE run_id = ? AND vbpl_id = ? AND endpoint = ?",
            (run_id, vbpl_id, endpoint)
        )
        if cursor.fetchone():
            return False

        relative_path = f"raw/{run_id}/{vbpl_id}-{endpoint}.json"
        full_path = self.db_path.parent / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

        with self.conn:
            self.conn.execute("""
                INSERT INTO raw_snapshots (run_id, vbpl_id, endpoint, content_hash, relative_path)
                VALUES (?, ?, ?, ?, ?)
            """, (run_id, vbpl_id, endpoint, content_hash, relative_path))
        return True

    def record_status(self, obs: StatusObservation) -> None:
        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO status_observations (vbpl_id, eff_status, eff_from, checked_at, content_hash, run_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (obs.vbpl_id, obs.eff_status, obs.eff_from, obs.checked_at.isoformat(), obs.content_hash, obs.run_id))

    def projection_matches(
        self,
        document_id: str,
        content: str,
        link: str,
        metadata: dict,
        run_id: str,
    ) -> bool:
        row = self.conn.execute(
            """SELECT content, link, metadata_json, run_id
               FROM onyx_projection WHERE document_id = ?""",
            (document_id,),
        ).fetchone()
        if row is None or row["run_id"] != run_id:
            return False
        try:
            stored_metadata = json.loads(row["metadata_json"])
        except json.JSONDecodeError:
            return False
        return (
            row["content"] == content
            and row["link"] == link
            and stored_metadata == metadata
        )

    def next_catalog_page(self, run_id: str) -> int:
        row = self.conn.execute(
            "SELECT next_catalog_page FROM crawl_checkpoints WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return int(row["next_catalog_page"]) if row else 1

    def record_catalog_page(self, run_id: str, page_number: int, vbpl_ids: list[str]) -> None:
        with self.conn:
            self.conn.executemany(
                """INSERT OR IGNORE INTO crawl_catalog_entries (run_id, vbpl_id, catalog_page)
                   VALUES (?, ?, ?)""",
                [(run_id, vbpl_id, page_number) for vbpl_id in vbpl_ids],
            )
            self.conn.execute(
                """INSERT INTO crawl_checkpoints (run_id, next_catalog_page)
                   VALUES (?, ?)
                   ON CONFLICT(run_id) DO UPDATE SET next_catalog_page = excluded.next_catalog_page""",
                (run_id, page_number + 1),
            )

    def catalog_ids(self, run_id: str) -> list[str]:
        rows = self.conn.execute(
            """SELECT vbpl_id FROM crawl_catalog_entries
               WHERE run_id = ? ORDER BY catalog_page, vbpl_id""",
            (run_id,),
        ).fetchall()
        return [str(row["vbpl_id"]) for row in rows]

    def record_reference(self, run_id: str, reference) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO legal_references
                   (run_id, from_vbpl_id, from_provision_key, to_vbpl_id, to_provision_key, relation_type, source_quote,
                    evidence_kind, evidence_reference, source_offset, resolution_state, evidence_hash, corpus_revision, searchable)
                   SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                   WHERE NOT EXISTS (
                       SELECT 1 FROM legal_references
                       WHERE run_id = ?
                         AND from_vbpl_id = ?
                         AND from_provision_key = ?
                         AND to_vbpl_id IS ?
                         AND to_provision_key IS ?
                         AND relation_type = ?
                         AND evidence_kind = ?
                   )""",
                (
                    run_id,
                    reference.from_vbpl_id,
                    reference.from_provision_key,
                    reference.to_vbpl_id,
                    reference.to_provision_key,
                    reference.relation_type,
                    reference.source_quote,
                    getattr(reference, "evidence_kind", "text_candidate"),
                    getattr(reference, "evidence_reference", ""),
                    getattr(reference, "source_offset", None),
                    getattr(reference, "resolution_state", "unresolved"),
                    getattr(reference, "evidence_hash", ""),
                    getattr(reference, "corpus_revision", run_id),
                    1 if getattr(reference, "searchable", False) else 0,
                    run_id,
                    reference.from_vbpl_id,
                    reference.from_provision_key,
                    reference.to_vbpl_id,
                    reference.to_provision_key,
                    reference.relation_type,
                    getattr(reference, "evidence_kind", "text_candidate"),
                ),
            )

    def latest_status(self, vbpl_id: str) -> StatusObservation | None:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT vbpl_id, eff_status, eff_from, checked_at, content_hash, run_id
            FROM status_observations
            WHERE vbpl_id = ?
            ORDER BY checked_at DESC
            LIMIT 1
        """, (vbpl_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return StatusObservation(
            vbpl_id=row["vbpl_id"],
            eff_status=row["eff_status"],
            eff_from=row["eff_from"],
            checked_at=datetime.fromisoformat(row["checked_at"]),
            content_hash=row["content_hash"],
            run_id=row["run_id"]
        )

    def finish_run(self, run_id: str, status: str, coverage: float) -> None:
        finished_at = datetime.now(UTC).isoformat()
        with self.conn:
            self.conn.execute("""
                UPDATE crawl_runs
                SET status = ?, coverage = ?, finished_at = ?
                WHERE run_id = ?
            """, (status, coverage, finished_at, run_id))

    def set_active_run(self, run_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM active_revision")
            self.conn.execute("""
                INSERT INTO active_revision (run_id, activated_at)
                VALUES (?, ?)
            """, (run_id, datetime.now(UTC).isoformat()))

    def get_active_run_id(self) -> str | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT run_id FROM active_revision LIMIT 1")
        row = cursor.fetchone()
        return row["run_id"] if row else None

    def get_run(self, run_id: str) -> CrawlRun | None:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT run_id, status, coverage, started_at, finished_at
            FROM crawl_runs
            WHERE run_id = ?
        """, (run_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return CrawlRun(
            run_id=row["run_id"],
            status=row["status"],
            coverage=row["coverage"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None
        )

    def record_release_run(
        self,
        run_id: str,
        status: str,
        manifest_path: str | None = None,
        manifest_sha256: str | None = None,
        document_count: int = 0,
    ) -> None:
        updated_at = datetime.now(UTC).isoformat()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO release_runs (run_id, status, manifest_path, manifest_sha256, document_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status = excluded.status,
                    manifest_path = excluded.manifest_path,
                    manifest_sha256 = excluded.manifest_sha256,
                    document_count = excluded.document_count,
                    updated_at = excluded.updated_at
                """,
                (run_id, status, manifest_path, manifest_sha256, document_count, updated_at),
            )

    def get_release_run(self, run_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT run_id, status, manifest_path, manifest_sha256, document_count, updated_at FROM release_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def get_catalog_entries_for_run(self, run_id: str) -> list[CatalogEntry]:
        rows = self.conn.execute(
            """SELECT vbpl_id, fingerprint, title, doc_num, doc_type, updated_date, eff_status, eff_to, raw_json
               FROM catalog_entries
               WHERE run_id = ?""",
            (run_id,),
        ).fetchall()
        result: list[CatalogEntry] = []
        for r in rows:
            try:
                raw_payload = json.loads(r["raw_json"])
            except Exception:
                raw_payload = {}
            result.append(
                CatalogEntry(
                    vbpl_id=r["vbpl_id"],
                    fingerprint=r["fingerprint"],
                    title=r["title"],
                    doc_num=r["doc_num"],
                    doc_type=r["doc_type"],
                    updated_date=r["updated_date"],
                    eff_status=r["eff_status"],
                    eff_to=r["eff_to"],
                    raw_payload=raw_payload,
                )
            )
        return result

    def record_catalog_scan(self, run_id: str, entries: list[CatalogEntry], complete: bool = True) -> None:
        started_at = datetime.now(UTC).isoformat()
        finished_at = started_at if complete else None
        with self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO catalog_scans (run_id, complete, item_count, started_at, finished_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (run_id, 1 if complete else 0, len(entries), started_at, finished_at),
            )
            self.conn.executemany(
                """INSERT OR REPLACE INTO catalog_entries
                   (run_id, vbpl_id, fingerprint, title, doc_num, doc_type, updated_date, eff_status, eff_to, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        run_id,
                        entry.vbpl_id,
                        entry.fingerprint,
                        entry.title,
                        entry.doc_num,
                        entry.doc_type,
                        entry.updated_date,
                        entry.eff_status,
                        entry.eff_to,
                        json.dumps(entry.raw_payload, ensure_ascii=False),
                    )
                    for entry in entries
                ],
            )

    def latest_successful_catalog_entries(self) -> dict[str, CatalogEntry]:
        row = self.conn.execute(
            """SELECT run_id FROM catalog_scans
               WHERE complete = 1
               ORDER BY started_at DESC, run_id DESC
               LIMIT 1"""
        ).fetchone()
        if not row:
            return {}
        latest_run_id = row["run_id"]
        rows = self.conn.execute(
            """SELECT vbpl_id, fingerprint, title, doc_num, doc_type, updated_date, eff_status, eff_to, raw_json
               FROM catalog_entries
               WHERE run_id = ?""",
            (latest_run_id,),
        ).fetchall()
        result: dict[str, CatalogEntry] = {}
        for r in rows:
            try:
                raw_payload = json.loads(r["raw_json"])
            except Exception:
                raw_payload = {}
            result[r["vbpl_id"]] = CatalogEntry(
                vbpl_id=r["vbpl_id"],
                fingerprint=r["fingerprint"],
                title=r["title"],
                doc_num=r["doc_num"],
                doc_type=r["doc_type"],
                updated_date=r["updated_date"],
                eff_status=r["eff_status"],
                eff_to=r["eff_to"],
                raw_payload=raw_payload,
            )
        return result

    def update_removal_candidates(self, current_scan_ids: set[str], run_id: str) -> tuple[list[str], list[str]]:
        known_rows = self.conn.execute(
            """SELECT DISTINCT vbpl_id FROM catalog_entries
               WHERE run_id IN (SELECT run_id FROM catalog_scans WHERE complete = 1)"""
        ).fetchall()
        all_known_ids = {r["vbpl_id"] for r in known_rows}
        if not all_known_ids:
            return ([], [])

        candidates: list[str] = []
        tombstones: list[str] = []

        with self.conn:
            absent_ids = all_known_ids - current_scan_ids
            for vbpl_id in absent_ids:
                existing = self.conn.execute(
                    "SELECT absence_count FROM catalog_removals WHERE vbpl_id = ?",
                    (vbpl_id,),
                ).fetchone()
                if not existing:
                    self.conn.execute(
                        """INSERT INTO catalog_removals (vbpl_id, absence_count, first_absent_run_id, last_absent_run_id, status)
                           VALUES (?, 1, ?, ?, 'candidate')""",
                        (vbpl_id, run_id, run_id),
                    )
                    candidates.append(vbpl_id)
                else:
                    new_count = existing["absence_count"] + 1
                    status = "tombstone" if new_count >= 2 else "candidate"
                    self.conn.execute(
                        """UPDATE catalog_removals
                           SET absence_count = ?, last_absent_run_id = ?, status = ?
                           WHERE vbpl_id = ?""",
                        (new_count, run_id, status, vbpl_id),
                    )
                    if status == "tombstone":
                        tombstones.append(vbpl_id)
                    else:
                        candidates.append(vbpl_id)

            for vbpl_id in current_scan_ids:
                self.conn.execute("DELETE FROM catalog_removals WHERE vbpl_id = ?", (vbpl_id,))

        return (candidates, tombstones)

    def get_tombstone_ids(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT vbpl_id FROM catalog_removals WHERE status = 'tombstone' ORDER BY vbpl_id"
        ).fetchall()
        return [r["vbpl_id"] for r in rows]

    def record_document_version(self, vbpl_id: str, version_id: str, fingerprint: str, run_id: str) -> None:
        created_at = datetime.now(UTC).isoformat()
        with self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO document_versions (vbpl_id, version_id, fingerprint, run_id, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (vbpl_id, version_id, fingerprint, run_id, created_at),
            )

    def record_delta_batch(self, manifest: DeltaManifest, manifest_path: str) -> None:
        batch_id = f"batch_{manifest.release_id}"
        with self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO delta_batches
                   (batch_id, release_id, parent_release_id, created_at, upsert_ids_json, tombstone_ids_json, manifest_path, checksum_sha256, acknowledged)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    batch_id,
                    manifest.release_id,
                    manifest.parent_release_id,
                    manifest.created_at,
                    json.dumps(manifest.upsert_ids),
                    json.dumps(manifest.tombstone_ids),
                    manifest_path,
                    manifest.checksum_sha256,
                ),
            )

    def pending_delta_batches(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT batch_id, release_id, parent_release_id, created_at, upsert_ids_json, tombstone_ids_json, manifest_path, checksum_sha256
               FROM delta_batches
               WHERE acknowledged = 0
               ORDER BY created_at ASC"""
        ).fetchall()
        res = []
        for r in rows:
            res.append({
                "batch_id": r["batch_id"],
                "release_id": r["release_id"],
                "parent_release_id": r["parent_release_id"],
                "created_at": r["created_at"],
                "upsert_ids": json.loads(r["upsert_ids_json"]),
                "tombstone_ids": json.loads(r["tombstone_ids_json"]),
                "manifest_path": r["manifest_path"],
                "checksum_sha256": r["checksum_sha256"],
            })
        return res

    def acknowledge_delta_batch(self, batch_id: str) -> None:
        now_iso = datetime.now(UTC).isoformat()
        with self.conn:
            self.conn.execute(
                """UPDATE delta_batches
                   SET acknowledged = 1, acknowledged_at = ?
                   WHERE batch_id = ?""",
                (now_iso, batch_id),
            )


