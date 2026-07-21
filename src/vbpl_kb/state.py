import sqlite3
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
            # legal_references
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS legal_references (
                    from_vbpl_id TEXT NOT NULL,
                    from_provision_key TEXT NOT NULL,
                    to_vbpl_id TEXT,
                    to_provision_key TEXT,
                    relation_type TEXT NOT NULL,
                    source_quote TEXT NOT NULL
                )
            """)
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
