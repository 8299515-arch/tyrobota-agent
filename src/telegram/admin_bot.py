import html
import structlog
from aiogram import Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func, desc, update
from src.config import settings
from src.database import AsyncSessionLocal
from src.models import Source, SourceStatus, Message, MessageStatus
from src.services.quiet import is_quiet_hours, quiet_label

logger = structlog.get_logger(__name__)


def _is_admin(user_id: int) -> bool:
    if user_id is None:
        return False
    if not settings.ADMIN_IDS:
        return False
    # Приводим к int для надежного сравнения
    admin_ids = [int(x) for x in settings.ADMIN_IDS if str(x).isdigit()]
    return user_id in admin_ids


def _uid(m: types.Message):
    return m.from_user.id if m.from_user else None


class AdminStates(StatesGroup):
    waiting_for_channel = State()
    confirm_reprocess = State()


def clean_channel_username(raw_text: str) -> str:
    text = (raw_text or "").strip()
    text = text.replace("https://t.me/", "").replace("http://t.me/", "").replace("t.me/", "")
    text = text.replace("@", "").strip("/").strip()
    return text


def setup_admin_handlers(dp: Dispatcher):
    @dp.message(Command("start"), StateFilter("*"))
    async def cmd_start(m: types.Message, state: FSMContext):
        await state.clear()
        if not _is_admin(_uid(m)):
            return
        qs = "night pause" if is_quiet_hours() else "day - accepting posts"
        text = (
            "<b>Tyrobota agent panel @tyrobota_kyiv_ua</b>\n\n"
            f"Mode now: <b>{qs}</b> ({quiet_label()})\n\n"
            "/stats - statistics\n"
            "/reprocess - reset cursors\n"
            "/sources - channels\n"
            "/add_source - add\n"
            "/remove_source - remove\n"
            "/errors - errors\n"
        )
        await m.answer(text, parse_mode="HTML")

    @dp.message(Command("stats"), StateFilter("*"))
    async def cmd_stats(m: types.Message, state: FSMContext):
        await state.clear()
        if not _is_admin(_uid(m)):
            return
        async with AsyncSessionLocal() as session:
            sources = await session.scalar(select(func.count(Source.id)))
            total = await session.scalar(select(func.count(Message.id)))
            published = await session.scalar(select(func.count(Message.id)).where(Message.status == MessageStatus.PUBLISHED))
            prefilter = await session.scalar(select(func.count(Message.id)).where(Message.status == MessageStatus.PREFILTER_DROPPED))
            rejected = await session.scalar(select(func.count(Message.id)).where(Message.status == MessageStatus.REJECTED))
            duplicates = await session.scalar(select(func.count(Message.id)).where(Message.status == MessageStatus.DUPLICATE))
            errors = await session.scalar(select(func.count(Message.id)).where(Message.status == MessageStatus.ERROR))
        qs = "night pause" if is_quiet_hours() else "day"
        text = (
            "<b>Stats:</b>\n\n"
            f"Sources: <b>{sources}</b>\n"
            f"Total: <b>{total}</b>\n"
            f"Published: <b>{published}</b>\n"
            f"Prefilter: <b>{prefilter}</b>\n"
            f"Rejected: <b>{rejected}</b>\n"
            f"Duplicates: <b>{duplicates}</b>\n"
            f"Errors: <b>{errors}</b>\n"
            f"Mode: <b>{qs}</b> ({quiet_label()})"
        )
        await m.answer(text, parse_mode="HTML")

    @dp.message(Command("reprocess"), StateFilter("*"))
    async def cmd_reprocess(m: types.Message, state: FSMContext):
        await state.clear()
        if not _is_admin(_uid(m)):
            return
        await state.set_state(AdminStates.confirm_reprocess)
        await m.answer("Reset ALL cursors to 0? Reply YES to confirm or /stats to cancel.")

    @dp.message(AdminStates.confirm_reprocess)
    async def reprocess_done(m: types.Message, state: FSMContext):
        if not _is_admin(_uid(m)):
            await state.clear()
            return
        if (m.text or "").strip().lower() not in ("yes", "y", "tak", "da"):
            await state.clear()
            await m.answer("Cancelled.")
            return
        async with AsyncSessionLocal() as session:
            await session.execute(update(Source).values(last_message_id=0))
            await session.commit()
        await state.clear()
        await m.answer("Counters reset. Agent will re-download posts.")

    @dp.message(Command("sources"), StateFilter("*"))
    async def cmd_sources(m: types.Message, state: FSMContext):
        await state.clear()
        if not _is_admin(_uid(m)):
            return
        async with AsyncSessionLocal() as session:
            srcs = (await session.execute(select(Source))).scalars().all()
        if not srcs:
            return await m.answer("No sources yet. Send /add_source")
        lines = ["<b>Channels:</b>"] + [f"- @{html.escape(s.channel)} last={s.last_message_id}" for s in srcs]
        await m.answer("\n".join(lines), parse_mode="HTML")

    @dp.message(Command("add_source"), StateFilter("*"))
    async def cmd_add_source(m: types.Message, state: FSMContext):
        if not _is_admin(_uid(m)):
            return
        await m.answer("Send channel username or link:")
        await state.set_state(AdminStates.waiting_for_channel)

    @dp.message(AdminStates.waiting_for_channel)
    async def add_source_done(m: types.Message, state: FSMContext):
        if not _is_admin(_uid(m)):
            await state.clear()
            return
        ch = clean_channel_username(m.text)
        if not ch:
            await m.answer("Cannot parse channel name. Try again:")
            return
        async with AsyncSessionLocal() as session:
            exists = await session.scalar(select(Source).where(Source.channel == ch))
            if exists:
                await m.answer(f"Channel @{html.escape(ch)} already exists.")
            else:
                session.add(Source(channel=ch, status=SourceStatus.ACTIVE))
                await session.commit()
                await m.answer(f"Channel @{html.escape(ch)} added.")
        await state.clear()

    @dp.message(Command("remove_source"), StateFilter("*"))
    async def cmd_remove_source(m: types.Message, state: FSMContext):
        await state.clear()
        if not _is_admin(_uid(m)):
            return
        parts = (m.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await m.answer("Usage: /remove_source channel")
            return
        ch = clean_channel_username(parts[1])
        async with AsyncSessionLocal() as session:
            obj = await session.scalar(select(Source).where(Source.channel == ch))
            if not obj:
                await m.answer(f"Channel @{html.escape(ch)} not found.")
                return
            await session.delete(obj)
            await session.commit()
        await m.answer(f"Channel @{html.escape(ch)} removed.")
        logger.info("source_removed", channel=ch, by=_uid(m))

    @dp.message(Command("errors"), StateFilter("*"))
    async def cmd_errors(m: types.Message, state: FSMContext):
        await state.clear()
        if not _is_admin(_uid(m)):
            return
        async with AsyncSessionLocal() as session:
            errs = (await session.execute(select(Message).where(Message.status == MessageStatus.ERROR).order_by(desc(Message.id)).limit(5))).scalars().all()
        if not errs:
            return await m.answer("No errors.")
        lines = ["<b>Last errors:</b>"]
        for e in errs:
            safe = html.escape((e.error_details or "")[:300])
            lines.append(f"- #{e.id}: {safe}")
        await m.answer("\n".join(lines), parse_mode="HTML")