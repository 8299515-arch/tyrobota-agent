import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler

import structlog
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

# Создание директории для логов при отсутствии
os.makedirs("logs", exist_ok=True)

# Настройка ротации логов (максимум 5 файлов по 10 МБ)
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
file_handler = RotatingFileHandler(
    filename="logs/bot.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8"
)
file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

# ВАЖНО: collector.py, admin_bot.py и pipeline.py логируют через structlog.
# Без этой настройки structlog по умолчанию пишет в stdout мимо RotatingFileHandler,
# а при запуске через pythonw.exe (без консоли) эти сообщения теряются безвозвратно —
# именно поэтому в logs/bot.log были видны только две строки "Запуск..." и ничего
# о реальной работе коллектора/пайплайна.
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.processors.KeyValueRenderer(key_order=["event"]),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = logging.getLogger(__name__)

from src.config import settings
from src.database import engine
from src.models import Base
from src.ai.openai_provider import OpenAIProvider
from src.services.pipeline import JobPipeline
from src.telegram.collector import TelegramCollector
from src.telegram.admin_bot import setup_admin_handlers


async def main():
    logger.info("Запуск Tyrobota Agent...")
    try:
        # Подстраховка: создаёт таблицы, если их ещё нет (на текущей базе они уже есть,
        # но это защищает от падения при разворачивании на новой машине/чистой БД).
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        bot = Bot(token=settings.BOT_TOKEN)
        dp = Dispatcher(storage=MemoryStorage())
        setup_admin_handlers(dp)

        ai_provider = OpenAIProvider()
        pipeline = JobPipeline(ai_provider=ai_provider, bot=bot)
        collector = TelegramCollector(pipeline)

        await collector.start()
        logger.info("Бот успешно запущен и готовит обработку данных.")

        try:
            await dp.start_polling(bot)
        finally:
            await collector.stop()
            await bot.session.close()

    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка бота по команде пользователя.")
    except Exception as e:
        logger.critical(f"Непредвиденное падение приложения: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
