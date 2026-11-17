from abc import ABC, abstractmethod
from src.schemas import JobExtractedData

class BaseAIProvider(ABC):
    @abstractmethod
    async def extract_job_data(self, raw_text: str) -> JobExtractedData:
        pass
