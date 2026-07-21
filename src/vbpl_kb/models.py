from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict

class StatusObservation(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    vbpl_id: str
    eff_status: str
    eff_from: str | None
    checked_at: datetime
    content_hash: str
    run_id: str

class LegalReference(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    from_vbpl_id: str
    from_provision_key: str
    to_vbpl_id: str | None
    to_provision_key: str | None
    relation_type: str  # cites, legal_basis, guides_implementation, amends, supplements, replaces, repeals, unknown
    source_quote: str

class CrawlRun(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    run_id: str
    status: str  # running, completed, failed, partial
    coverage: float
    started_at: datetime
    finished_at: datetime | None

class OnyxDocument(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    document_id: str
    content: str
    link: str
    metadata: dict[str, Any]
