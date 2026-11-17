from typing import List, Optional
from pydantic import BaseModel, Field

class JobExtractedData(BaseModel):
    is_job_offer: bool = Field(description="Является ли предложением работы")
    is_scam_or_ad: bool = Field(description="Является ли спамом/рекламой")
    title: Optional[str] = Field(None, description="Должность")
    category: Optional[str] = Field(None, description="Категория")
    company: Optional[str] = Field(None, description="Компания")
    city: Optional[str] = Field(None, description="Город")
    district: Optional[str] = Field(None, description="Район")
    address: Optional[str] = Field(None, description="Адрес")
    salary: Optional[str] = Field(None, description="Зарплата")
    currency: Optional[str] = Field("грн", description="Валюта")
    salary_min: Optional[int] = Field(None)
    salary_max: Optional[int] = Field(None)
    schedule: Optional[str] = Field(None, description="График")
    employment_type: Optional[str] = Field(None)
    responsibilities: Optional[List[str]] = Field(default_factory=list)
    requirements: Optional[List[str]] = Field(default_factory=list)
    contact: Optional[str] = Field(None)
    rejection_reason: Optional[str] = Field(None)

class QualityScoreResult(BaseModel):
    score: int
    grade: str
    passed: bool
    reasons: List[str] = Field(default_factory=list)

class DeduplicationResult(BaseModel):
    is_duplicate: bool
    duplicate_of_id: Optional[int] = None
    similarity_score: float = 0.0
