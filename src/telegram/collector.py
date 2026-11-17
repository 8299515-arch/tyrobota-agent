import asyncio
import os
import time
from typing import Optional
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat
from telethon.errors import (
    FloodWaitError,
    ChannelPrivateError,
    ChannelInvalidError,
    UsernameInvalidError,
)
from sqlalchemy import select
from src.database import AsyncSessionLocal
from src.models import Source, SourceStatus, MessageStatus
from src.services.pipeline import JobPipeline
from src.services.quiet import is_quiet_hours, just_after_quiet, quiet_label
from src.config import settings
import structlog

logger = structlog.get_logger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LAST_CYCLE_FILE = os.path.join(_BASE_DIR, "logs", "last_cycle.txt")


class TelegramCollector:
    def __init__(self, pipeline: JobPipeline):
        self.pipeline = pipeline
        self.client = TelegramClient(
            settings.TELEGRAM_SESSION_NAME,
            settings.TELEGRAM_API_ID,
            settings.TELEGRAM_API_HASH,
        )
        self.is_running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._announce_sent_for_date: Optional[str] = None
        self._last_cycle_ts: float = self._load_last_cycle()

    def _load_last_cycle(self) -> float:
        try:
            with open(_LAST_CYCLE_FILE, "r", encoding="utf-8") as f:
                return float((f.read() or "0").strip() or 0)
        except Exception:
            return 0.0

    def _save_last_cycle(self, ts: float) -> None:
        try:
            os.makedirs(os.path.dirname(_LAST_CYCLE_FILE), exist_ok=True)
            with open(_LAST_CYCLE_FILE, "w", encoding="utf-8") as f:
                f.write(str(int(ts)))
        except Exception:
            pass

    async def start(self):
        logger.info("starting_telethon_collector")
        await self.client.start()
        self.is_running = True
        if not self._last_cycle_ts:
            self._last_cycle_ts = time.time()
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        self.is_running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        await self.client.disconnect()

    async def _poll_loop(self):
        while self.is_running:
            try:
                await self._collect_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("collector_error", error=str(e))
            await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)

    def _is_stale_startup(self) -> bool:
        if not self._last_cycle_ts:
            return True
        return (time.time() - self._last_cycle_ts) > settings.QUIET_STALE_SKIP_HOURS * 3600

    async def _maybe_announce_quiet(self):
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            try:
                now = datetime.now(ZoneInfo(settings.QUIET_TZ))
            except Exception:
                from datetime import timezone
                now = datetime.now(timezone.utc).astimezone()

            today = now.strftime("%Y-%m-%d")
            if self._announce_sent_for_date == today:
                return
            if not settings.QUIET_ANNOUNCE.strip():
                return

            cur = now.hour * 60 + now.minute
            start = settings.QUIET_START_HOUR * 60 + settings.QUIET_START_MINUTE
            announce_at = (start - settings.QUIET_ANNOUNCE_BEFORE_MIN) % 1440
            delta = (cur - announce_at) % 1440

            if delta <= 4 and not is_quiet_hours(now):
                try:
                    await self.pipeline.bot.send_message(
                        chat_id=settings.TARGET_CHANNEL_ID,
                        text=settings.QUIET_ANNOUNCE,
                    )
                    logger.info("quiet_announce_sent")
                except Exception as e:
                    logger.error("quiet_announce_failed", error=str(e)[:300])
                self._announce_sent_for_date = today
        except Exception as e:
            logger.error("quiet_announce_check_failed", error=str(e)[:300])

    async def _collect_once(self):
        await self._maybe_announce_quiet()
        quiet = is_quiet_hours()
        grace = just_after_quiet() if not quiet else False
        stale = self._is_stale_startup()
        skip_backlog = quiet or grace or stale

        if skip_backlog:
            why = "quiet" if quiet else ("morning-grace" if grace else "stale-startup")
            logger.info("collector_skip_backlog", reason=why, label=quiet_label())

        self._last_cycle_ts = time.time()
        self._save_last_cycle(self._last_cycle_ts)

        async with AsyncSessionLocal() as session:
            sources = (await session.execute(
                select(Source).where(Source.status == SourceStatus.ACTIVE)
            )).scalars().all()

        for src in sources:
            if not self.is_running:
                break
            try:
                entity = await self.client.get_entity(src.channel)
                messages = await self.client.get_messages(entity, limit=15, min_id=src.last_message_id)

                if not messages:
                    continue

                if skip_backlog:
                    newest = max(m.id for m in messages)
                    async with AsyncSessionLocal() as session:
                        src_db = await session.get(Source, src.id)
                        if src_db and newest > src_db.last_message_id:
                            src_db.last_message_id = newest
                            await session.commit()
                            logger.info("skip_backlog_forwarded", source=src.channel, count=len(messages), new_last=newest)
                    continue

                username = getattr(entity, "username", None)

                # Используем единую сессию на канал
                async with AsyncSessionLocal() as session:
                    src_db = await session.get(Source, src.id)
                    if not src_db:
                        continue

                    for msg in reversed(messages):
                        if not self.is_running:
                            break

                        text = (getattr(msg, "raw_text", None) or msg.text or "").strip()
                        if not text:
                            if msg.id > src_db.last_message_id:
                                src_db.last_message_id = msg.id
                                await session.commit()
                            continue

                        src_url = f"https://t.me/{username}/{msg.id}" if username else None

                        # Передаем управление в пайплайн
                        result = await self.pipeline.process_raw_message(session, src_db, msg.id, text, src_url)

                        if result == MessageStatus.ERROR:
                            logger.warning("message_processing_error_cursor_not_advanced", source=src.channel, msg_id=msg.id)
                            continue

                        if msg.id > src_db.last_message_id:
                            src_db.last_message_id = msg.id
                            await session.commit()

                        # Пауза между сообщениями для контроля Rate Limits
                        await asyncio.sleep(2.5)

            except FloodWaitError as fwe:
                logger.warning("flood_wait_encountered", seconds=fwe.seconds)
                await asyncio.sleep(fwe.seconds + 2)
            except (ChannelPrivateError, ChannelInvalidError, UsernameInvalidError, ValueError) as err:
                logger.error("source_access_error_disabling", source=src.channel, error=str(err))
                # Помечаем недоступный источник как неактивный
                async with AsyncSessionLocal() as session:
                    src_db = await session.get(Source, src.id)
                    if src_db:
                        src_db.status = SourceStatus.DISABLED
                        await session.commit()
            except Exception as e:
                logger.error("source_poll_failed", source=src.channel, error=str(e)[:500])