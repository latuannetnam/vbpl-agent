from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any, Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from vbpl_kb.canonicalize import CanonicalInstrumentDraft, compute_node_id
from vbpl_kb.db_models import (
    AcceptanceRun,
    CatalogObservation,
    CatalogScan,
    ConnectorDelivery,
    EvidenceDependency,
    EvidenceObject as EvidenceObjectORM,
    Instrument,
    InstrumentVersion,
    LegalNode,
    RemovalCandidate,
)
from vbpl_kb.evidence import EvidenceObject
from vbpl_kb.legal_tree import LegalNodeDraft
from vbpl_kb.catalog import parse_vbpl_id_int, CatalogEntry, CatalogChangeSet


@dataclass(frozen=True)
class InstrumentVersionResult:
    instrument_id: str
    version_id: str
    is_new_version: bool
    node_count: int


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
            v_id = parse_vbpl_id_int(entry.vbpl_id)
            curr_entries_by_id[v_id] = entry

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

        # Determine absent IDs
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

        for v_id in curr_ids:
            cand_obj = self.session.scalar(select(RemovalCandidate).where(RemovalCandidate.vbpl_id == v_id))
            if cand_obj and cand_obj.status != "cleared":
                cand_obj.status = "cleared"
                cand_obj.consecutive_absence_count = 0
                cand_obj.updated_at = now
                cleared_ids.append(v_id)

        for v_id in absent_ids:
            cand_obj = self.session.scalar(select(RemovalCandidate).where(RemovalCandidate.vbpl_id == v_id))
            if not cand_obj:
                new_cand = RemovalCandidate(
                    vbpl_id=v_id,
                    official_source_id=str(v_id),
                    first_absent_scan_id=scan_id,
                    consecutive_absence_count=1,
                    status="candidate",
                    updated_at=now,
                )
                self.session.add(new_cand)
                removal_candidate_ids.append(v_id)
            elif cand_obj.status == "candidate" or cand_obj.consecutive_absence_count == 1:
                cand_obj.consecutive_absence_count = 2
                cand_obj.status = "tombstoned"
                cand_obj.updated_at = now
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


class CanonicalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_observation(
        self, draft: CanonicalInstrumentDraft, nodes: Sequence[LegalNodeDraft]
    ) -> InstrumentVersionResult:
        now = datetime.now(timezone.utc)
        instrument = self.session.get(Instrument, draft.instrument_id)
        if not instrument:
            instrument = Instrument(
                id=draft.instrument_id,
                official_source_id=draft.official_source_id,
                title=draft.title,
                number=draft.number,
                issue_date=draft.issue_date,
                effective_date=draft.effective_date,
                current_status=draft.current_status,
                first_observed_at=now,
                last_observed_at=now,
            )
            self.session.add(instrument)
        else:
            instrument.title = draft.title
            instrument.number = draft.number
            instrument.issue_date = draft.issue_date
            instrument.effective_date = draft.effective_date
            instrument.current_status = draft.current_status
            instrument.last_observed_at = now

        existing_version = self.session.get(InstrumentVersion, draft.version_id)
        if existing_version:
            self.session.flush()
            return InstrumentVersionResult(
                instrument_id=draft.instrument_id,
                version_id=draft.version_id,
                is_new_version=False,
                node_count=len(nodes),
            )

        # Create new immutable version
        version = InstrumentVersion(
            id=draft.version_id,
            instrument_id=draft.instrument_id,
            detail_payload_hash=draft.detail_payload_hash,
            normalized_content_hash=draft.normalized_content_hash,
            raw_evidence_hash=draft.raw_evidence_hash,
            created_at=now,
        )
        self.session.add(version)
        self.session.flush()

        path_to_node_id: dict[str, str] = {}
        for draft_node in nodes:
            n_id = compute_node_id(draft.version_id, draft_node.node_type, draft_node.materialized_path)
            path_to_node_id[draft_node.materialized_path] = n_id

        for draft_node in nodes:
            n_id = path_to_node_id[draft_node.materialized_path]
            parent_path = "/".join(draft_node.materialized_path.split("/")[:-1])
            parent_id = path_to_node_id.get(parent_path)

            node_orm = LegalNode(
                id=n_id,
                version_id=draft.version_id,
                parent_node_id=parent_id,
                node_type=draft_node.node_type,
                display_label=draft_node.display_label,
                normalized_coordinate=draft_node.normalized_coordinate,
                heading=draft_node.heading,
                sibling_ordinal=draft_node.sibling_ordinal,
                materialized_path=draft_node.materialized_path,
                text=draft_node.text,
                lead_in_text=draft_node.lead_in_text,
                source_anchor=draft_node.source_anchor,
                source_start=draft_node.source_start,
                source_end=draft_node.source_end,
                content_hash=draft_node.content_hash,
                parse_status=draft_node.parse_status,
            )
            self.session.add(node_orm)

        self.session.flush()
        return InstrumentVersionResult(
            instrument_id=draft.instrument_id,
            version_id=draft.version_id,
            is_new_version=True,
            node_count=len(nodes),
        )


class ReleaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def mark_connector_applied(
        self,
        release_id: str,
        corpus_view: str,
        connector_name: str,
        connector_id: int,
        attempt_id: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        delivery = self.session.scalar(
            select(ConnectorDelivery).where(
                ConnectorDelivery.release_id == release_id,
                ConnectorDelivery.connector_name == connector_name,
            )
        )
        if not delivery:
            delivery = ConnectorDelivery(
                release_id=release_id,
                corpus_view=corpus_view,
                connector_name=connector_name,
                connector_id=connector_id,
                attempt_id=attempt_id,
                status="applied",
                applied_at=now,
            )
            self.session.add(delivery)
        else:
            delivery.attempt_id = attempt_id
            delivery.status = "applied"
            delivery.applied_at = now
        self.session.flush()

    def mark_accepted(
        self,
        release_id: str,
        agent_profile: str,
        report_hash: str,
        report_data: dict[str, Any],
    ) -> None:
        now = datetime.now(timezone.utc)
        run = AcceptanceRun(
            release_id=release_id,
            agent_profile=agent_profile,
            report_hash=report_hash,
            report_data=report_data,
            status="accepted",
            evaluated_at=now,
        )
        self.session.add(run)
        self.session.flush()
