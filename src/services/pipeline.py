from datetime import datetime, timezone
import html
from typing import Optional
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas import JobExtractedData
from src.models import Message, Job, Duplicate, MessageStatus, Source
from src.filters.prefilter import FastPreFilter
from src.filters.dedup import DeduplicationEngine
from src.ai.base import BaseAIProvider
from src.services.scorer import QualityScorer
from src.services.formatter import JobPostFormatter
from src.services.quiet import is_quiet_hours, quiet_label
from aiogram import Bot
from src.config import settings
import structlog

logger = structlog.get_logger(__name__)


def _utcnow():
    return datetime.now(timezone.utc)


class JobPipeline:
    def __init__(self, ai_provider: BaseAIProvider, bot: Bot):
        self.ai = ai_provider
        self.bot = bot
        self.dedup = DeduplicationEngine(threshold=settings.DEDUP_SIMILARITY_THRESHOLD)

    async def process_raw_message(
        self,
        session: AsyncSession,
        source: Source,
        telegram_message_id: int,
        raw_text: str,
        source_url: Optional[str] = None,
    ) -> MessageStatus:
        logger.info("processing_message", source=source.channel, msg_id=telegram_message_id)

        # 1. Идемпотентность: проверять, не был ли пост уже обработан
        existing = await session.scalar(
            select(Message).where(
                Message.source_id == source.id,
                Message.telegram_message_id == telegram_message_id,
            )
        )
        if existing:
            logger.info("message_already_processed", msg_id=telegram_message_id, status=str(existing.status))
            if existing.status != MessageStatus.ERROR:
                return existing.status
            db_message = existing
        else:
            # 2. Проверка тихих часов только для нового сообщения
            if is_quiet_hours():
                db_message = Message(
                    source_id=source.id,
                    telegram_message_id=telegram_message_id,
                    text=raw_text,
                    status=MessageStatus.PREFILTER_DROPPED,
                    error_details=f"Ночная пауза {quiet_label()} — пост пропущен",
                    processed_at=_utcnow(),
                )
                session.add(db_message)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                return MessageStatus.PREFILTER_DROPPED

            # 3. Фиксация получения сообщения в базе
            db_message = Message(
                source_id=source.id,
                telegram_message_id=telegram_message_id,
                text=raw_text,
                status=MessageStatus.RECEIVED,
            )
            session.add(db_message)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                return MessageStatus.DUPLICATE

        # 4. Быстрый префильтр
        is_cand, reason = FastPreFilter.inspect(raw_text, settings.MIN_TEXT_LENGTH, settings.MAX_TEXT_LENGTH)
        if not is_cand:
            db_message.status = MessageStatus.PREFILTER_DROPPED
            db_message.error_details = reason
            db_message.processed_at = _utcnow()
            await session.commit()
            return MessageStatus.PREFILTER_DROPPED

        # 5. Извлечение данных через AI
        try:
            extracted: JobExtractedData = await self.ai.extract_job_data(raw_text)
        except Exception as e:
            db_message.status = MessageStatus.ERROR
            db_message.error_details = str(e)[:1000]
            db_message.processed_at = _utcnow()
            await session.commit()
            return MessageStatus.ERROR

        # 6. Оценка качества данных
        quality = QualityScorer.evaluate(extracted)
        if not quality.passed or not extracted.title:
            db_message.status = MessageStatus.REJECTED
            db_message.error_details = f"Score: {quality.score}. Reasons: {', '.join(quality.reasons)}"
            db_message.processed_at = _utcnow()
            await session.commit()
            return MessageStatus.REJECTED

        # 7. Поиск дубликатов
        dedup = await self.dedup.find_duplicate(
            session=session,
            candidate_title=extracted.title,
            candidate_text=raw_text,
            candidate_contact=extracted.contact,
            candidate_company=extracted.company,
        )

        if dedup.is_duplicate and dedup.duplicate_of_id:
            db_message.status = MessageStatus.DUPLICATE
            db_message.error_details = f"Duplicate of #{dedup.duplicate_of_id}"
            db_message.processed_at = _utcnow()
            session.add(Duplicate(message_id=db_message.id, duplicate_of=dedup.duplicate_of_id, similarity=dedup.similarity_score))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
            return MessageStatus.DUPLICATE

        # 8. Создание объекта вакансии
        job = Job(
            message_id=db_message.id,
            title=extracted.title,
            category=extracted.category or "Другое",
            company=extracted.company,
            city=extracted.city,
            district=extracted.district,
            address=extracted.address,
            salary=extracted.salary,
            currency=extracted.currency,
            salary_min=extracted.salary_min,
            salary_max=extracted.salary_max,
            schedule=extracted.schedule,
            employment_type=extracted.employment_type,
            requirements="\n".join(extracted.requirements) if extracted.requirements else None,
            responsibilities="\n".join(extracted.responsibilities) if extracted.responsibilities else None,
            contact=extracted.contact,
            source_url=source_url,
            score=quality.score,
            grade=quality.grade,
        )
        session.add(job)
        try:
            await session.flush()
        except Exception as e:
            logger.error("job_flush_error", error=str(e))
            await session.rollback()
            return MessageStatus.ERROR

        # 9. Публикация поста в Telegram-канал
        try:
            post = JobPostFormatter.format_telegram_message(extracted, source_url)
            sent = await self.bot.send_message(
                chat_id=settings.TARGET_CHANNEL_ID,
                text=post,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            job.published_message_id = sent.message_id
            job.published_at = _utcnow()
            db_message.status = MessageStatus.PUBLISHED
            db_message.processed_at = _utcnow()
            await session.commit()
            return MessageStatus.PUBLISHED
        except Exception as e:
            logger.error("publish_message_failed", error=str(e))
            # Если отправка с HTML упала, делаем фоллбэк с экранированием текста
            try:
                safe_post = html.escape(JobPostFormatter.format_telegram_message(extracted, source_url))
                sent = await self.bot.send_message(
                    chat_id=settings.TARGET_CHANNEL_ID,
                    text=safe_post,
                    disable_web_page_preview=True,
                )
                job.published_message_id = sent.message_id
                job.published_at = _utcnow()
                db_message.status = MessageStatus.PUBLISHED
                db_message.processed_at = _utcnow()
                await session.commit()
                return MessageStatus.PUBLISHED
            except Exception as fallback_err:
                db_message.status = MessageStatus.ERROR
                db_message.error_details = f"Publish error: {str(fallback_err)[:1000]}"
                db_message.processed_at = _utcnow()
                await session.commit()
                return MessageStatus.ERROR