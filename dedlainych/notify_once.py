"""Real scheduled work; never sends keepalive traffic to a sleeping web service."""

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from dedlainych.config import settings
from dedlainych.db.session import make_database
from dedlainych.services.inbox import drain
from dedlainych.services.notifications import Notifier, scheduler_lock
from dedlainych.telegram.dispatcher import build_dispatcher


async def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    config = settings()
    if not config.bot_token.get_secret_value():
        raise RuntimeError("Нужен GitHub Actions secret BOT_TOKEN")
    engine, sessions = make_database()
    lock = None
    bot = Bot(config.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        try:
            lock = await scheduler_lock(engine)
        except RuntimeError:
            logging.warning("Отправитель уже работает; параллельный запуск пропущен")
            return
        # Recover durable updates if Render was interrupted; original attachments remain available.
        await drain(sessions, bot, build_dispatcher(sessions, config), limit=25)
        await Notifier(sessions, bot).tick()
    finally:
        await bot.session.close()
        if lock:
            await lock.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
