from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

ToneType = Literal["business", "casual", "executive"]
ModeType = Literal["sequential", "langgraph"]


class GenerateDraftRequest(BaseModel):
    target_date: str = Field(..., description="YYYY-MM-DD")
    max_articles: int = Field(default=5, ge=1, le=10)
    tone: ToneType = "business"
    mode: ModeType = "sequential"
    filter_economic_only: bool = True

    @field_validator("target_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        datetime.strptime(v, "%Y-%m-%d")
        return v


class SourceItem(BaseModel):
    title: str
    url: str


class EconomicJudgment(BaseModel):
    is_economic: bool = True
    confidence: int = 5
    category: str = "other"
    reason: str = ""


class ArticleDetail(BaseModel):
    title: str
    url: str
    published_at: str = ""
    judgment: EconomicJudgment
    used_in_summary: bool = False
    summary: str = ""


class GenerateDraftResponse(BaseModel):
    target_date: str
    collected_articles: int
    used_articles: int
    subject: str
    body: str
    sources: List[SourceItem]
    warnings: Optional[List[str]] = None
    mode: ModeType = "sequential"
    article_details: List[ArticleDetail] = Field(default_factory=list)
