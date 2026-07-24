import sqlite3
import json
from datetime import datetime, UTC
from pathlib import Path
from vbpl_kb.models import StatusObservation, CrawlRun

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

