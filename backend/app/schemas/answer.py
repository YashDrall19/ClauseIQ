from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Source(BaseModel):
    page: int = Field(ge=1)
    excerpt: str = Field(min_length=1, max_length=2000)
    section_title: str | None = None


class Answer(BaseModel):
    answer: str = Field(min_length=1, max_length=5000)
    confidence_score: float = Field(ge=0, le=1)
    found_in_contract: bool
    sources: list[Source]


class AnalysisItem(BaseModel):
    question_id: str
    question: str
    status: Literal["completed", "failed"]
    answer: Answer | None = None
    error: str | None = None


class AnalysisResponse(BaseModel):
    contract_id: str
    status: Literal["completed", "partial", "failed"]
    answers: list[AnalysisItem]


class ModelAnswer(BaseModel):
    question_id: str | None = None
    answer: str = Field(min_length=1, max_length=5000)
    found_in_contract: bool
    source_ids: list[str] = Field(default_factory=list)


class ModelBatchAnswer(BaseModel):
    answers: list[ModelAnswer]


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)

    @field_validator("question")
    @classmethod
    def reject_blank_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question cannot be blank")
        return value.strip()


class ChatResponse(Answer):
    contract_id: str


class UploadResponse(BaseModel):
    contract_id: str
    filename: str
    page_count: int | None
    extraction_method: str
    processing_status: str
    analysis_status: str
    answers: list[AnalysisItem] | None = None


class ContractSummary(BaseModel):
    contract_id: str
    filename: str
    uploaded_at: str
    processing_status: str
    page_count: int | None
    extraction_method: str
    analysis_status: str


class ContractDetail(ContractSummary):
    answers: list[AnalysisItem] | None


class ContractListResponse(BaseModel):
    items: list[ContractSummary]
    page: int
    page_size: int
    total: int
