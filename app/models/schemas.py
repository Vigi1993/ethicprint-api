from typing import Optional
from pydantic import BaseModel


class BrandProposalIn(BaseModel):
    name: str
    sector_key: Optional[str] = None
    website: Optional[str] = None
    reason: Optional[str] = None
    submitter: Optional[str] = None


class SourceProposalIn(BaseModel):
    brand_id: int
    category_key: str
    url: str
    title: Optional[str] = None
    publisher: Optional[str] = None
    summary: Optional[str] = None
    submitter: Optional[str] = None


class ErrorReportIn(BaseModel):
    brand_id: int
    category_key: Optional[str] = None
    description: str
    source_url: Optional[str] = None
    submitter: Optional[str] = None


class ApproveProposalBody(BaseModel):
    confirmed_judgment: Optional[str] = None


class CriterionSourceScoreIn(BaseModel):
    brand_id: int
    criterion_id: int
    source_id: int
    tier: int
    judgment: str
    notes: Optional[str] = None


class ExclusionIn(BaseModel):
    brand_id: int
    criterion_id: int
