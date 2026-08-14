from enum import StrEnum

from pydantic import BaseModel, Field


class Side(StrEnum):
    petitioner = "petitioner"
    respondent = "respondent"
    neutral = "neutral"


class CaseMetadata(BaseModel):
    title: str | None = None
    court: str = "Supreme Court of India"
    petitioner: str | None = None
    respondent: str | None = None
    judgment_date: str | None = None
    bench: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    acts: list[str] = Field(default_factory=list)
    source_uri: str
    document_sha256: str


class CanonicalPage(BaseModel):
    schema_version: str = "1.0"
    case: CaseMetadata
    page_number: int
    paragraph_ids: list[str] = Field(default_factory=list)
    text: str
    text_base64: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=8000)
    side: Side = Side.neutral
    session_id: str | None = None
    conversation: list[dict[str, str]] = Field(default_factory=list)


class Citation(BaseModel):
    source: str
    page: int
    excerpt: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    warnings: list[str] = Field(default_factory=lambda: ["Verify citations and current law before use in court."])


class UploadResponse(BaseModel):
    session_id: str
    filename: str
    pages: int
    sha256: str