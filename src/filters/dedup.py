import hashlib
import re
from typing import Optional
from rapidfuzz import fuzz
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import Job
from src.schemas import DeduplicationResult

class DeduplicationEngine:
    def __init__(self, threshold: float = 0.82):
        self.threshold = threshold

    @staticmethod
    def clean_text_for_hash(text: str) -> str:
        text = text.lower()
        text = re.sub(r"http\S+|www\S+|t\.me\S+", "", text)
        text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
        return " ".join(text.split())

    async def find_duplicate(
        self,
        session: AsyncSession,
        candidate_title: str,
        candidate_text: str,
        candidate_contact: Optional[str] = None,
        candidate_company: Optional[str] = None,
        limit_recent: int = 150,
    ) -> DeduplicationResult:
        norm_candidate = self.clean_text_for_hash(candidate_text)
        stmt = select(Job).order_by(desc(Job.id)).limit(limit_recent)
        recent_jobs = (await session.execute(stmt)).scalars().all()

        for job in recent_jobs:
            if candidate_contact and job.contact:
                clean_cand = re.sub(r"[^\w@+]", "", candidate_contact.lower())
                clean_job = re.sub(r"[^\w@+]", "", job.contact.lower())
                if clean_cand == clean_job and len(clean_cand) > 5:
                    title_sim = fuzz.ratio(candidate_title.lower(), job.title.lower()) / 100.0
                    if title_sim > 0.60:
                        return DeduplicationResult(is_duplicate=True, duplicate_of_id=job.id, similarity_score=max(0.95, title_sim))

            job_text = f"{job.title} {job.responsibilities or ''} {job.requirements or ''}"
            norm_job = self.clean_text_for_hash(job_text)
            similarity = fuzz.token_sort_ratio(norm_candidate, norm_job) / 100.0
            if similarity >= self.threshold:
                return DeduplicationResult(is_duplicate=True, duplicate_of_id=job.id, similarity_score=similarity)

        return DeduplicationResult(is_duplicate=False)
