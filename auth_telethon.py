import asyncio
from telethon import TelegramClient
from src.config import settings

async def main():
    print("Инициализация подключения к Telegram...")
    client = TelegramClient(
        settings.TELEGRAM_SESSION_NAME,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH
    )
    await client.start()
    print("\n✅ Авторизация успешна! Файл сессии сохранен.")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())