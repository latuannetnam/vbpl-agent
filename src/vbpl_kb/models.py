from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict


class StatusObservation(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    vbpl_id: str
    eff_status: str
    eff_from: str | None
    checked_at: datetime
    content_hash: str
    run_id: str
    status_source: str = "api"

class LegalReference(BaseModel):
    model_config = ConfigDict(frozen=True)
    from_vbpl_id: str
    from_provision_key: str
    to_vbpl_id: str | None
    to_provision_key: str | None
    relation_type: Literal[
        "cites", "legal_basis", "details", "implements", "delegated_by",
        "amends", "supplements", "replaces", "repeals", "suspends",
        "continues_effect", "unknown"
    ]
    evidence_kind: Literal["official_structured", "official_page", "text_candidate"]
    evidence_reference: str
    source_quote: str
    source_offset: int | None
    resolution_state: Literal["verified", "resolved_citation", "candidate", "unmapped", "unresolved"]
    evidence_hash: str
    corpus_revision: str
    searchable: bool

class CrawlRun(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    run_id: str
    status: str  # running, completed, failed, partial
    coverage: float
    started_at: datetime
    finished_at: datetime | None

class OnyxSection(BaseModel):
    model_config = ConfigDict(frozen=True)
    section_id: str
    text: str
    link: str

class OnyxDocument(BaseModel):
    model_config = ConfigDict(frozen=True)
    projection_schema_version: Literal[2] = 2
    document_id: str
    sections: tuple[OnyxSection, ...]
    link: str
    metadata: dict[str, Any]

    @property
    def content(self) -> str:
        return "\n\n".join(section.text for section in self.sections)

class ReleaseManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    release_id: str
    manifest_path: Path
    manifest_sha256: str
    document_count: int
    section_count: int = 0
    projection_schema_version: int = 2
    published_at: str = ""
    documents: list[dict[str, Any]] = []

class ActiveRelease(BaseModel):
    model_config = ConfigDict(frozen=True)

    release_id: str
    manifest_path: str
    manifest_sha256: str
    published_at: str


class AuthorityClassification(BaseModel):
    model_config = ConfigDict(frozen=True)
    hierarchy_regime: str
    article4_order: int | None
    normative_form: str
    authority_group: str
    issuer_type: str
    classification_status: Literal[
        "known", "unknown", "not_normative", "legacy_transitional"
    ]
    classification_source: str
    classification_version: str
    is_normative: bool


class ApplicabilityEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)
    legal_status_raw: str
    legal_status_normalized: str
    verified_at: str
    status_source: str
    effective_from: str
    effective_to: str
    jurisdiction_level: Literal[
        "national", "province", "commune", "special_zone",
        "legacy_district", "unknown"
    ]
    jurisdiction_code: str
    jurisdiction_name: str
    transitional_until: str
    source_url: str
    corpus_revision: str
    status_evidence_hash: str


class Provision(BaseModel):
    model_config = ConfigDict(frozen=True)
    provision_key: str
    article_number: str
    clause_number: str
    point_label: str
    provision_heading: str
    citation_structure: Literal["parsed", "unparsed"]
    text: str
