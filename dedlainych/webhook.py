import asyncio
import hmac
import logging
import os
import signal
from urllib.parse import urlsplit

from aiohttp import web
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from pydantic import ValidationError
from sqlalchemy import select

from dedlainych.db.models import Admin
from dedlainych.db.session import make_database
from dedlainych.services.inbox import drain, enqueue
from dedlainych.telegram.dispatcher import build_dispatcher

log = logging.getLogger(__name__)


def build_app(config, sessions, bot, dispatcher, *, manage_lifecycle=True) -> web.Application:
    secret = config.webhook_secret.get_secret_value()
    if not secret:
        raise ValueError("Для webhook задайте WEBHOOK_SECRET в окружении")
    app = web.Application(client_max_size=1024 * 1024)
    workers: set[asyncio.Task] = set()

    async def consume():
        try:
            while await drain(sessions, bot, dispatcher) == 25:
                pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("Очередь webhook отложена: %s", type(exc).__name__)

    def kick():
        if not workers:
            task = asyncio.create_task(consume())
            workers.add(task)
            task.add_done_callback(workers.discard)

    async def receive(request: web.Request):
        supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(supplied.encode(), secret.encode()):
            raise web.HTTPForbidden()
        try:
            update = Update.model_validate(await request.json(), context={"bot": bot})
        except (ValueError, ValidationError):
            raise web.HTTPBadRequest() from None
        try:
            await enqueue(sessions, update)
        except Exception as exc:
            log.error("Webhook не сохранён: %s", type(exc).__name__)
            # Telegram will retry; do not acknowledge an update that is not durable.
            raise web.HTTPServiceUnavailable() from None
        kick()
        return web.json_response({"ok": True})

    async def health(request):
        # No keepalive query or scheduler here: database and Render may sleep normally.
        return web.json_response({"ok": True, "mode": "webhook"})

    async def startup(app):
        if manage_lifecycle:
            base = (config.webhook_base_url or os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/")
            parsed = urlsplit(base)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.query
                or parsed.fragment
                or parsed.path
            ):
                raise ValueError("WEBHOOK_BASE_URL должен быть HTTPS-адресом сервиса без пути")
            async with sessions() as session:
                existing = set((await session.scalars(select(Admin.user_id))).all())
                for uid in config.admin_ids:
                    if uid not in existing:
                        session.add(Admin(user_id=uid))
                await session.commit()
            await bot.set_webhook(
                base + "/telegram/webhook",
                secret_token=secret,
                allowed_updates=dispatcher.resolve_used_update_types(),
                max_connections=1,
                drop_pending_updates=False,
            )
            log.info(
                "Webhook подключён. Встроенный планировщик выключен; уведомления запускаются отдельным заданием."
            )
        kick()

    async def cleanup(app):
        # Leave the webhook configured so Telegram can wake the sleeping Render service.
        pending = set()
        if workers:
            _, pending = await asyncio.wait(list(workers), timeout=20)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    app.router.add_get("/health", health)
    app.router.add_post("/telegram/webhook", receive)
    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
    return app


async def serve(config):
    engine, sessions = make_database()
    bot = Bot(config.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    runner = web.AppRunner(
        build_app(config, sessions, bot, build_dispatcher(sessions, config)), access_log=None
    )
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, stopped.set)
    try:
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", config.port).start()
        await stopped.wait()
    finally:
        loop.remove_signal_handler(signal.SIGTERM)
        await runner.cleanup()
        await bot.session.close()
        await engine.dispose()
