from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.services.status_labels import INFORMATIONAL_DISCLAIMER, format_status_es


class SourceMatch(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    status: str
    source_url: str | None = None
    published_at: datetime | None = None

    @computed_field
    @property
    def estado(self) -> str:
        return format_status_es(self.status)


class PersonMatch(BaseModel):
    full_name: str
    document_id_last4: str | None = None
    document_id_hash: str | None = None
    status: str = "unknown"
    confidence_score: float = Field(..., ge=0, le=100)
    sources: list[SourceMatch]
    status_conflict: bool = False
    source_count: int = 0
    latest_published_at: datetime | None = None

    @computed_field
    @property
    def estado(self) -> str:
        return format_status_es(self.status)


class SearchResponse(BaseModel):
    query: str
    matches: list[PersonMatch]
    disclaimer: str = Field(default=INFORMATIONAL_DISCLAIMER)
    debug: "SearchDebugInfo | None" = None


class ProviderDebugInfo(BaseModel):
    name: str
    enabled: bool
    status: str
    reason: str | None = None
    degraded_until: datetime | None = None
    raw_count: int
    mapped_count: int
    filtered_count: int
    error: str | None = None


class SearchDebugInfo(BaseModel):
    providers: list[ProviderDebugInfo]
