from datetime import datetime, date
from typing import Any, Optional
import uuid
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

# Cross-dialect JSON type (JSONB on PostgreSQL, JSON on SQLite)
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    revision: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    report: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONType, nullable=True)


class CatalogScan(Base):
    __tablename__ = "catalog_scans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        CheckConstraint("status IN ('running', 'complete', 'failed')", name="ck_catalog_scan_status"),
        nullable=False,
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entries_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CatalogObservation(Base):
    __tablename__ = "catalog_observations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("catalog_scans.id"), nullable=False)
    vbpl_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    official_source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    catalog_entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    detail_payload_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RemovalCandidate(Base):
    __tablename__ = "removal_candidates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vbpl_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    official_source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    first_absent_scan_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("catalog_scans.id"), nullable=False)
    consecutive_absence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(32),
        CheckConstraint("status IN ('candidate', 'tombstoned', 'cleared')", name="ck_removal_candidate_status"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvidenceObject(Base):
    __tablename__ = "evidence_objects"

    hash_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    official_url: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    corpus_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONType, nullable=True)


class EvidenceDependency(Base):
    __tablename__ = "evidence_dependencies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(256), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), ForeignKey("evidence_objects.hash_sha256"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[str] = mapped_column(String(256), primary_key=True)  # vbpl:<id>
    official_source_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    number: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    current_status: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InstrumentVersion(Base):
    __tablename__ = "instrument_versions"

    id: Mapped[str] = mapped_column(String(256), primary_key=True)  # ver:<hash>
    instrument_id: Mapped[str] = mapped_column(String(256), ForeignKey("instruments.id"), nullable=False)
    detail_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_evidence_hash: Mapped[str] = mapped_column(String(64), ForeignKey("evidence_objects.hash_sha256"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("instrument_id", "detail_payload_hash", "normalized_content_hash", name="uq_instrument_version_hashes"),
    )


class LegalNode(Base):
    __tablename__ = "legal_nodes"

    id: Mapped[str] = mapped_column(String(256), primary_key=True)  # node:<hash>
    version_id: Mapped[str] = mapped_column(String(256), ForeignKey("instrument_versions.id"), nullable=False)
    parent_node_id: Mapped[Optional[str]] = mapped_column(String(256), ForeignKey("legal_nodes.id"), nullable=True)
    node_type: Mapped[str] = mapped_column(
        String(32),
        CheckConstraint("node_type IN ('part', 'chapter', 'article', 'clause', 'point')", name="ck_legal_node_type"),
        nullable=False,
    )
    display_label: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_coordinate: Mapped[str] = mapped_column(String(256), nullable=False)
    heading: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sibling_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    materialized_path: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[Text] = mapped_column(Text, nullable=False)
    lead_in_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_anchor: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    source_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parse_status: Mapped[str] = mapped_column(
        String(32),
        CheckConstraint("parse_status IN ('verified_structured', 'verified_text', 'heuristic', 'unparsed')", name="ck_legal_node_parse_status"),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("version_id", "materialized_path", name="uq_legal_node_materialized_path"),
        UniqueConstraint("version_id", "parent_node_id", "node_type", "normalized_coordinate", name="uq_legal_node_coordinate"),
    )


class AuthorityRegime(Base):
    __tablename__ = "authority_regimes"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    regime_version: Mapped[str] = mapped_column(String(64), nullable=False)
    regime_data: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuthorityClassification(Base):
    __tablename__ = "authority_classifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[str] = mapped_column(String(256), ForeignKey("instrument_versions.id"), nullable=False)
    regime_id: Mapped[str] = mapped_column(String(128), ForeignKey("authority_regimes.id"), nullable=False)
    form: Mapped[str] = mapped_column(String(128), nullable=False)
    issuer: Mapped[str] = mapped_column(String(256), nullable=False)
    statutory_group: Mapped[str] = mapped_column(String(128), nullable=False)
    order_string: Mapped[str] = mapped_column(String(64), nullable=False)
    classification_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StatusObservation(Base):
    __tablename__ = "status_observations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instrument_id: Mapped[str] = mapped_column(String(256), ForeignKey("instruments.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(128), nullable=False)
    verification_source: Mapped[str] = mapped_column(String(128), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), ForeignKey("evidence_objects.hash_sha256"), nullable=False)
    raw_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONType, nullable=True)


class ApplicabilityEnvelope(Base):
    __tablename__ = "applicability_envelopes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[str] = mapped_column(String(256), ForeignKey("instrument_versions.id"), nullable=False)
    node_id: Mapped[Optional[str]] = mapped_column(String(256), ForeignKey("legal_nodes.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(128), nullable=False)
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    jurisdiction: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_tokens: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    is_current_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exclusion_reasons: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LegalRelation(Base):
    __tablename__ = "legal_relations"

    id: Mapped[str] = mapped_column(String(256), primary_key=True)
    source_version_id: Mapped[str] = mapped_column(String(256), ForeignKey("instrument_versions.id"), nullable=False)
    source_node_id: Mapped[Optional[str]] = mapped_column(String(256), ForeignKey("legal_nodes.id"), nullable=True)
    target_instrument_id: Mapped[Optional[str]] = mapped_column(String(256), ForeignKey("instruments.id"), nullable=True)
    target_version_id: Mapped[Optional[str]] = mapped_column(String(256), ForeignKey("instrument_versions.id"), nullable=True)
    target_node_id: Mapped[Optional[str]] = mapped_column(String(256), ForeignKey("legal_nodes.id"), nullable=True)
    relation_type: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    is_verified_effect: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_hash: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("evidence_objects.hash_sha256"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    logical_edge_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReleaseRun(Base):
    __tablename__ = "release_runs"

    id: Mapped[str] = mapped_column(String(256), primary_key=True)  # release_id
    revision: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        CheckConstraint("status IN ('candidate', 'promoted', 'connector_applied', 'accepted', 'blocked')", name="ck_release_run_status"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    validation_report: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONType, nullable=True)


class ReleaseView(Base):
    __tablename__ = "release_views"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    release_id: Mapped[str] = mapped_column(String(256), ForeignKey("release_runs.id"), nullable=False)
    corpus_view: Mapped[str] = mapped_column(
        String(32),
        CheckConstraint("corpus_view IN ('current', 'history', 'evidence')", name="ck_release_view_corpus_view"),
        nullable=False,
    )
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shard_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_ids_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("release_id", "corpus_view", name="uq_release_view_release_corpus"),
    )


class ConnectorDelivery(Base):
    __tablename__ = "connector_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    release_id: Mapped[str] = mapped_column(String(256), ForeignKey("release_runs.id"), nullable=False)
    corpus_view: Mapped[str] = mapped_column(String(32), nullable=False)
    connector_name: Mapped[str] = mapped_column(String(128), nullable=False)
    connector_id: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("release_id", "connector_name", name="uq_connector_delivery_release_connector"),
    )


class AcceptanceRun(Base):
    __tablename__ = "acceptance_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    release_id: Mapped[str] = mapped_column(String(256), ForeignKey("release_runs.id"), nullable=False)
    agent_profile: Mapped[str] = mapped_column(String(128), nullable=False)
    report_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    report_data: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
