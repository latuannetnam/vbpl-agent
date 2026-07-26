from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from vbpl_kb.db_models import (
    CatalogObservation,
    CatalogScan,
    EvidenceDependency,
    EvidenceObject as EvidenceObjectORM,
    RemovalCandidate,
)
from vbpl_kb.evidence import EvidenceObject
from vbpl_kb.models import CatalogEntry


@dataclass(frozen=True)
class CatalogChangeSet:
    upsert_ids: list[int]
    removal_candidate_ids: list[int]
    tombstone_ids: list[int]
    cleared_ids: list[int]


class CatalogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def begin_scan(self, run_id: uuid.UUID | None = None) -> uuid.UUID:
        scan = CatalogScan(
            run_id=run_id,
            started_at=datetime.now(timezone.utc),
            status="running",
            entries_count=0,
        )
        self.session.add(scan)
        self.session.flush()
        return scan.id

    def fail_scan(self, scan_id: uuid.UUID, reason: str) -> None:
        scan = self.session.get(CatalogScan, scan_id)
        if scan:
            scan.status = "failed"
            scan.reason = reason
            scan.finished_at = datetime.now(timezone.utc)
            self.session.flush()

    def complete_scan(self, scan_id: uuid.UUID, entries: Sequence[CatalogEntry]) -> CatalogChangeSet:
        scan = self.session.get(CatalogScan, scan_id)
        if not scan:
            raise ValueError(f"Scan {scan_id} not found")

        now = datetime.now(timezone.utc)
        scan.finished_at = now
        scan.entries_count = len(entries)

        # Get previous completed scan baseline
        stmt_prev = (
            select(CatalogScan.id)
            .where(CatalogScan.status == "complete", CatalogScan.id != scan_id)
            .order_by(CatalogScan.finished_at.desc())
            .limit(1)
        )
        prev_scan_id = self.session.scalar(stmt_prev)

        prev_observations: dict[int, str] = {}
        if prev_scan_id:
            stmt_obs = select(CatalogObservation).where(CatalogObservation.scan_id == prev_scan_id)
            for obs in self.session.scalars(stmt_obs):
                prev_observations[obs.vbpl_id] = obs.catalog_entry_hash

        curr_entries_by_id: dict[int, CatalogEntry] = {}
        curr_entry_hashes: dict[int, str] = {}

        for entry in entries:
            v_id = int(entry.vbpl_id)
            curr_entries_by_id[v_id] = entry
            # Hash entry fields
            h = hashlib.sha256(
                f"{entry.vbpl_id}:{entry.title}:{entry.doc_num}:{entry.doc_type}:{entry.eff_status}".encode()
            ).hexdigest()
            curr_entry_hashes[v_id] = h

            obs = CatalogObservation(
                scan_id=scan_id,
                vbpl_id=v_id,
                official_source_id=str(entry.vbpl_id),
                catalog_entry_hash=h,
                observed_at=now,
            )
            self.session.add(obs)

        # Determine upserts (new or changed fingerprint)
        upsert_ids: list[int] = []
        for v_id, h in curr_entry_hashes.items():
            prev_h = prev_observations.get(v_id)
            if prev_h is None or prev_h != h:
                upsert_ids.append(v_id)

        # Determine absent IDs (present in previous baseline or existing pending candidates, but missing now)
        prev_ids = set(prev_observations.keys())
        curr_ids = set(curr_entry_hashes.keys())
        absent_ids = (prev_ids - curr_ids)

        stmt_pending = select(RemovalCandidate).where(RemovalCandidate.status == "candidate")
        for cand in self.session.scalars(stmt_pending):
            if cand.vbpl_id not in curr_ids:
                absent_ids.add(cand.vbpl_id)

        removal_candidate_ids: list[int] = []
        tombstone_ids: list[int] = []
        cleared_ids: list[int] = []

        # Handle cleared candidates (reappeared)
        for v_id in curr_ids:
            cand = self.session.scalar(select(RemovalCandidate).where(RemovalCandidate.vbpl_id == v_id))
            if cand and cand.status != "cleared":
                cand.status = "cleared"
                cand.consecutive_absence_count = 0
                cand.updated_at = now
                cleared_ids.append(v_id)

        # Handle absent candidates (two-scan rule)
        for v_id in absent_ids:
            cand = self.session.scalar(select(RemovalCandidate).where(RemovalCandidate.vbpl_id == v_id))
            if not cand:
                cand = RemovalCandidate(
                    vbpl_id=v_id,
                    official_source_id=str(v_id),
                    first_absent_scan_id=scan_id,
                    consecutive_absence_count=1,
                    status="candidate",
                    updated_at=now,
                )
                self.session.add(cand)
                removal_candidate_ids.append(v_id)
            elif cand.status == "candidate" or cand.consecutive_absence_count == 1:
                cand.consecutive_absence_count = 2
                cand.status = "tombstoned"
                cand.updated_at = now
                tombstone_ids.append(v_id)

        scan.status = "complete"
        self.session.flush()

        return CatalogChangeSet(
            upsert_ids=upsert_ids,
            removal_candidate_ids=removal_candidate_ids,
            tombstone_ids=tombstone_ids,
            cleared_ids=cleared_ids,
        )


class EvidenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def persist_evidence_metadata(self, obj: EvidenceObject) -> None:
        existing = self.session.get(EvidenceObjectORM, obj.hash_sha256)
        if not existing:
            orm_obj = EvidenceObjectORM(
                hash_sha256=obj.hash_sha256,
                media_type=obj.media_type,
                official_url=obj.official_url,
                endpoint=obj.endpoint,
                acquired_at=obj.acquired_at,
                corpus_revision=obj.corpus_revision,
                size_bytes=obj.size_bytes,
            )
            self.session.add(orm_obj)
            self.session.flush()

    def record_dependency(self, entity_type: str, entity_id: str, evidence_hash: str) -> None:
        dep = EvidenceDependency(
            entity_type=entity_type,
            entity_id=entity_id,
            evidence_hash=evidence_hash,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(dep)
        self.session.flush()
