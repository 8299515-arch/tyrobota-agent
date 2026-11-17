code = '''import asyncio
import json
import re
import structlog
from openai import AsyncOpenAI
from src.ai.base import BaseAIProvider
from src.ai.prompts import SYSTEM_EXTRACTOR_PROMPT
from src.schemas import JobExtractedData
from src.config import settings

logger = structlog.get_logger(__name__)

# Проверенные поддерживаемые модели Groq
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
]

def clean_and_parse_json(raw_content: str) -> dict:
    raw_content = raw_content.strip()
    if "```" in raw_content:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_content, re.DOTALL)
        if match:
            raw_content = match.group(1)
    
    start = raw_content.find("{")
    end = raw_content.rfind("}")
    if start != -1 and end != -1:
        raw_content = raw_content[start : end + 1]
    
    return json.loads(raw_content)

class OpenAIProvider(BaseAIProvider):
    def __init__(self):
        self.is_groq = settings.OPENAI_API_KEY.startswith("gsk_")
        if self.is_groq:
            self.client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url="https://api.groq.com/openai/v1",
                timeout=settings.AI_TIMEOUT_SECONDS,
            )
            self.current_model_idx = 0
            self.model = GROQ_MODELS[0]
        else:
            self.client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                timeout=settings.AI_TIMEOUT_SECONDS,
            )
            self.model = settings.OPENAI_MODEL

    async def extract_job_data(self, raw_text: str) -> JobExtractedData:
        await asyncio.sleep(0.5)

        attempts = len(GROQ_MODELS) if self.is_groq else 1
        last_exception = None

        for _ in range(attempts):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                SYSTEM_EXTRACTOR_PROMPT
                                + "\\nReturn strictly a valid raw JSON object. Do not include markdown codeblocks or explanation."
                            ),
                        },
                        {"role": "user", "content": f"JOB TEXT:\\n{raw_text}"},
                    ],
                    temperature=0.1,
                )
                raw_content = response.choices[0].message.content or "{}"
                parsed_json = clean_and_parse_json(raw_content)
                return JobExtractedData.model_validate(parsed_json)

            except Exception as e:
                err_str = str(e)
                last_exception = e
                if self.is_groq and ("429" in err_str or "rate_limit" in err_str or "400" in err_str or "decommissioned" in err_str or "model_not_found" in err_str):
                    self.current_model_idx = (self.current_model_idx + 1) % len(GROQ_MODELS)
                    old_model = self.model
                    self.model = GROQ_MODELS[self.current_model_idx]
                    logger.warning("switching_groq_model", old=old_model, new=self.model)
                    await asyncio.sleep(1.5)
                    continue
                else:
                    logger.error("ai_extraction_failed", error=err_str)
                    raise

        if last_exception:
            raise last_exception
'''

with open('src/ai/openai_provider.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("ФАЙЛ УСПЕШНО ОБНОВЛЕН БЕЗ ОШИБОК СИНТАКСИСА!")