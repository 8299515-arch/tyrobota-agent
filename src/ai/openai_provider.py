import asyncio
import json
import re

import structlog
from openai import AsyncOpenAI

from src.ai.base import BaseAIProvider
from src.ai.prompts import SYSTEM_EXTRACTOR_PROMPT
from src.config import settings
from src.schemas import JobExtractedData

logger = structlog.get_logger(__name__)

GROQ_MODELS = [
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
]


def build_job_json_schema() -> dict:
    schema = JobExtractedData.model_json_schema()
    properties = schema["properties"]

    # Only the truly required fields should be enforced in the structured response.
    # Optional fields are valid to omit; forcing every property to appear makes the
    # model produce noisy or invalid payloads and breaks extraction on sparse vacancies.
    schema["required"] = ["is_job_offer", "is_scam_or_ad"]
    schema["additionalProperties"] = False

    return schema


def clean_and_parse_json(raw_content: str) -> dict:
    if not raw_content or not raw_content.strip():
        raise ValueError("AI returned an empty response")

    raw_content = raw_content.strip()

    if "```" in raw_content:
        match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            raw_content,
            re.DOTALL,
        )
        if match:
            raw_content = match.group(1)

    start = raw_content.find("{")
    end = raw_content.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("AI response does not contain a JSON object")

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
        if not raw_text or not raw_text.strip():
            raise ValueError("Cannot analyze empty job text")

        await asyncio.sleep(0.5)

        attempts = len(GROQ_MODELS) if self.is_groq else 1
        last_exception = None

        for attempt in range(attempts):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                SYSTEM_EXTRACTOR_PROMPT
                                + "\n\n"
                                "Return only one valid JSON object. "
                                "The fields is_job_offer and is_scam_or_ad "
                                "are mandatory and must always be present."
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"JOB TEXT:\n{raw_text}",
                        },
                    ],
                    temperature=0.1,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "job_extracted_data",
                            "strict": True,
                            "schema": build_job_json_schema(),
                        },
                    },
                )

                raw_content = response.choices[0].message.content

                if not raw_content:
                    raise ValueError("AI returned an empty response")

                parsed_json = clean_and_parse_json(raw_content)

                return JobExtractedData.model_validate(parsed_json)

            except Exception as e:
                err_str = str(e)
                last_exception = e

                logger.error(
                    "ai_extraction_failed",
                    model=self.model,
                    attempt=attempt + 1,
                    error=err_str,
                )

                if (
                    self.is_groq
                    and attempt + 1 < attempts
                    and (
                        "model_not_found" in err_str
                        or "does not exist" in err_str
                        or "decommissioned" in err_str
                        or ("429" in err_str and ("TPD" in err_str or "tokens per day" in err_str))
                    )
                ):
                    old_model = self.model
                    self.current_model_idx += 1
                    self.model = GROQ_MODELS[self.current_model_idx]

                    logger.warning(
                        "switching_groq_model",
                        old=old_model,
                        new=self.model,
                    )

                    await asyncio.sleep(1.5)
                    continue

                raise

        if last_exception:
            raise last_exception

        raise RuntimeError("AI extraction failed")