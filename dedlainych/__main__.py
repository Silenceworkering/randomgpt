import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, text

from dedlainych.config import settings
from dedlainych.db.models import Admin
from dedlainych.db.session import make_database
from dedlainych.services.notifications import Notifier, scheduler_lock
from dedlainych.telegram.handlers import UI

log = logging.getLogger(__name__)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # HTTP client debug logs can contain tokens in URL paths. Keep them disabled.
    for name in ["httpx", "httpcore", "aiogram.event"]:
        logging.getLogger(name).setLevel(logging.WARNING)
    config = settings()
    if not config.bot_token.get_secret_value():
        raise RuntimeError("Укажи BOT_TOKEN в окружении; токен не нужно добавлять в GitHub")
    engine, sessions = make_database()
    lock = await scheduler_lock(engine)
    bot = Bot(config.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    scheduler = AsyncIOScheduler(timezone="UTC")
    dispatcher = Dispatcher()
    dispatcher.include_router(UI(sessions, config).router)

    @dispatcher.errors()
    async def errors(event: ErrorEvent):
        # Exception strings may include remote URLs or message data, so log only exception type.
        log.error("Ошибка обработки Telegram: %s", type(event.exception).__name__)
        if event.update.callback_query:
            try:
                await event.update.callback_query.answer(
                    "💀 Не получилось. Попробуй снова чуть позже.", show_alert=True
                )
            except Exception:
                pass
        return True

    async def watch_lock():
        if engine.dialect.name != "postgresql":
            return
        backend = await lock.scalar(text("SELECT pg_backend_pid()"))
        while True:
            await asyncio.sleep(10)
            try:
                if lock.invalidated or await lock.scalar(text("SELECT pg_backend_pid()")) != backend:
                    raise RuntimeError("Утрачена блокировка экземпляра")
            except Exception:
                log.error("Соединение блокировки потеряно; остановка для безопасного перезапуска")
                scheduler.pause()
                await dispatcher.stop_polling()
                return

    watcher = None
    try:
        async with sessions() as session:
            existing = set((await session.scalars(select(Admin.user_id))).all())
            for uid in config.admin_ids:
                if uid not in existing:
                    session.add(Admin(user_id=uid))
            await session.commit()
        notifier = Notifier(sessions, bot)
        scheduler.add_job(
            notifier.tick,
            "interval",
            seconds=30,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
            id="personal_summaries",
        )
        scheduler.start()
        await bot.delete_webhook(drop_pending_updates=False)
        watcher = asyncio.create_task(watch_lock())
        await dispatcher.start_polling(
            bot, allowed_updates=dispatcher.resolve_used_update_types(), close_bot_session=False
        )
    finally:
        if watcher:
            watcher.cancel()
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await bot.session.close()
        await lock.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
