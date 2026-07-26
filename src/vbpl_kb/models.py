from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Provision:
    provision_key: str = ""
    text: str = ""
    heading: str | None = None
    article_number: str = ""
    clause_number: str = ""
    point_label: str = ""
    provision_heading: str = ""
    citation_structure: str = "parsed"


@dataclass(frozen=True)
class LegalReference:
    from_vbpl_id: str = ""
    from_provision_key: str | None = None
    to_vbpl_id: str | None = None
    to_provision_key: str | None = None
    relation_type: str = ""
    evidence_kind: str = "text_candidate"
    evidence_reference: str = ""
    source_quote: str | None = None
    source_offset: Any = None
    resolution_state: str = "unresolved"
    evidence_hash: str = ""
    corpus_revision: str = ""
    searchable: bool = False
    quote: str | None = None
    target_vbpl_id: str = ""


@dataclass(frozen=True)
class OnyxSection:
    section_id: str = ""
    text: str = ""
    link: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "section_id": self.section_id,
            "text": self.text,
            "link": self.link,
        }


@dataclass(frozen=True)
class OnyxDocument:
    document_id: str = ""
    sections: tuple[OnyxSection, ...] = ()
    link: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    projection_schema_version: int = 2
    raw_content: str = ""

    @property
    def content(self) -> str:
        if self.raw_content:
            return self.raw_content
        return "\n\n".join(s.text for s in self.sections)

    def to_dict(self) -> dict[str, Any]:
        return {
            "projection_schema_version": self.projection_schema_version,
            "document_id": self.document_id,
            "sections": [s.to_dict() if hasattr(s, "to_dict") else s for s in self.sections],
            "link": self.link,
            "metadata": self.metadata,
            "content": self.content,
        }


@dataclass(frozen=True)
class AuthorityClassification:
    hierarchy_regime: str = ""
    article4_order: int | None = None
    normative_form: str = ""
    authority_group: str = ""
    issuer_type: str = ""
    classification_status: str = ""
    classification_source: str = ""
    classification_version: str = ""
    is_normative: bool = True


@dataclass(frozen=True)
class ApplicabilityEnvelope:
    jurisdiction_level: str = ""
    legal_status: str = ""
    verified_at: Any = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    effective_from: Any = None
    effective_to: Any = None
    temporal_status: str = ""
    status_source: str = ""
    subject_scope: str = ""
    is_in_force: bool = True
    legal_status_raw: str = ""
    legal_status_normalized: str = ""
    jurisdiction_code: str = ""
    jurisdiction_name: str = ""
    transitional_until: str = ""
    source_url: str = ""
    corpus_revision: str = ""
    status_evidence_hash: str = ""


@dataclass(frozen=True)
class CatalogEntry:
    vbpl_id: str | int
    title: str
    doc_num: str | None = None
    doc_type: str | None = None
    updated_date: str | None = None
    eff_status: str | None = None
    eff_to: str | None = None
    fingerprint: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CatalogChangeSet:
    upsert_ids: list[int]
    removal_candidate_ids: list[int]
    tombstone_ids: list[int]
    cleared_ids: list[int]


@dataclass(frozen=True)
class ActiveRelease:
    release_id: str
    manifest_path: str
    manifest_sha256: str
    published_at: str


@dataclass(frozen=True)
class ReleaseManifest:
    release_id: str
    manifest_path: Path
    manifest_sha256: str
    document_count: int
    section_count: int
    projection_schema_version: int
    published_at: str = ""
    documents: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class StatusObservation:
    vbpl_id: str
    eff_status: str
    eff_from: str | None
    checked_at: datetime
    content_hash: str
    run_id: str
    status_source: str = "api"


@dataclass(frozen=True)
class CrawlRun:
    run_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    coverage: float


@dataclass(frozen=True)
class DeltaManifest:
    release_id: str
    parent_release_id: str | None
    upsert_ids: list[str]
    tombstone_ids: list[str]
    created_at: str
    checksum_sha256: str
