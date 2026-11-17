import os
from typing import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from src.config import settings


def _resolve_db_url(url: str) -> str:
    # sqlite+aiosqlite:///tyrobota.db -> абсолютный путь от корня проекта
    if url.startswith("sqlite") and ":///" in url:
        prefix, rel = url.split("///", 1)
        rel = rel.strip()
        is_abs = rel.startswith("/") or (len(rel) > 2 and rel[1] == ":") or rel.startswith("\\\\")
        if rel and not is_abs:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            abs_path = os.path.join(base, rel).replace(os.sep, "/")
            return f"{prefix}///{abs_path}"
    return url


db_url = _resolve_db_url(settings.DATABASE_URL)
is_sqlite = db_url.startswith("sqlite")

# Для SQLite убираем pool_size/max_overflow, настраиваем параметры под SQLite
if is_sqlite:
    engine = create_async_engine(
        db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    # Включаем WAL-режим и внешние ключи для SQLite при каждом подключении
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")  # Ожидание 5 сек при конкурентной записи
        cursor.close()

else:
    # Конфигурация для PostgreSQL/MySQL
    engine = create_async_engine(
        db_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=False,
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise