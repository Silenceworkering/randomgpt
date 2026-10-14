import asyncio
import hmac
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import urlsplit
import anyio
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from aiogram import Bot
from aiogram.types import Update
from pydantic import ValidationError
from .catalog import ITEMS, CATEGORIES, DATA, public_item
from .schemas import BuildRequest, RecommendRequest, CompareRequest
from .engine import evaluate, recommend, NoBuildError
from .bot import create_dispatcher, register_webhook
from .prices import BOOK

load_dotenv()
logger = logging.getLogger("voltrix")
STATIC = Path(__file__).parent / "static"


def valid_public_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and parsed.path in ("", "/")
            and (parsed.port is None or 1 <= parsed.port <= 65535)
        )
    except ValueError:
        return False


async def recommend_async(req):
    # Serialize CPU-bound exhaustive search; other routes remain responsive.
    async with app.state.search_lock:
        return await anyio.to_thread.run_sync(recommend, req)


async def setup_bot(bot, url, secret):
    delay = 5
    while True:
        try:
            await register_webhook(bot, url, secret)
            app.state.bot_ready = True
            logger.info("Telegram webhook registered")
            return
        except Exception:
            # Never log exception text: Telegram client errors can contain token URLs.
            logger.warning(
                "Telegram registration failed; retrying in %s seconds", delay
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


@asynccontextmanager
async def lifespan(application):
    application.state.search_lock = asyncio.Lock()
    application.state.bot = None
    application.state.bot_ready = False
    application.state.dispatcher = None
    application.state.processed_updates = {}
    application.state.webhook_lock = asyncio.Lock()
    application.state.webhook_secret = ""
    task = None
    price_task = (
        asyncio.create_task(BOOK.run())
        if os.getenv("PRICES_AUTO_REFRESH", "true").lower() == "true"
        else None
    )
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    url = (
        os.getenv("PUBLIC_BASE_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
    ).rstrip("/")
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if token:
        if not valid_public_url(url) or not re.fullmatch(
            r"[A-Za-z0-9_-]{32,256}", secret
        ):
            logger.error(
                "Telegram disabled: configure public HTTPS URL and 32–256 character webhook secret"
            )
        else:
            try:
                bot = Bot(token=token)
                application.state.bot = bot
                application.state.webhook_secret = secret
                application.state.dispatcher = create_dispatcher(recommend_async, url)
                task = asyncio.create_task(setup_bot(bot, url, secret))
            except Exception:
                logger.error("Telegram disabled: invalid bot configuration")
    try:
        yield
    finally:
        if price_task:
            price_task.cancel()
            with suppress(asyncio.CancelledError):
                await price_task
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if application.state.bot:
            await application.state.bot.session.close()
        # Do not delete webhook on shutdown: Render may stop/restart at any time.


app = FastAPI(title="VOLTRIX API", version="1.1.0", lifespan=lifespan)


@app.middleware("http")
async def limits_and_headers(request: Request, call_next):
    if request.method == "POST":
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > 65536):
            return JSONResponse({"detail": "Слишком большой запрос."}, status_code=413)
        # ASGI stream cap also protects against chunked bodies without Content-Length.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 65536:
                return JSONResponse(
                    {"detail": "Слишком большой запрос."}, status_code=413
                )
        request._body = bytes(body)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    logger.error("Unhandled application error: %s", type(exc).__name__)
    return JSONResponse(
        {"detail": "Временная ошибка сервиса. Попробуйте ещё раз."}, status_code=500
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "telegram_configured": app.state.bot is not None,
        "telegram_registered": app.state.bot_ready,
        "version": "1.1.0",
        "pricing_mode": "retailer",
        "price_refreshing": BOOK.refreshing,
        "price_last_refresh_at": BOOK.last_refresh_at,
    }


@app.get("/api/catalog")
async def catalog():
    snapshot = BOOK.snapshot()
    return {
        "items": [public_item(i, snapshot) for i in ITEMS.values()],
        "categories": CATEGORIES,
        "metadata": DATA["metadata"],
        "price_status": {
            "refreshing": BOOK.refreshing,
            "last_refresh_at": BOOK.last_refresh_at,
            "priced_items": sum(BOOK.best(i, snapshot) is not None for i in ITEMS),
            "max_age_hours": 24,
        },
    }


@app.post("/api/build/check")
async def build_check(req: BuildRequest):
    return evaluate(req)


@app.post("/api/recommend")
async def recommend_route(req: RecommendRequest):
    try:
        return await recommend_async(req)
    except NoBuildError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/compare")
async def compare(req: CompareRequest):
    snapshot = BOOK.snapshot()
    items = [public_item(ITEMS[i], snapshot) for i in req.ids]
    keys = sorted(set().union(*(i["specs"] for i in items)))
    return {
        "items": items,
        "rows": [
            {"key": key, "values": [i["specs"].get(key) for i in items]} for key in keys
        ],
    }


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    if not app.state.bot:
        raise HTTPException(503, "Telegram-бот не настроен.")
    supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(supplied.encode(), app.state.webhook_secret.encode()):
        raise HTTPException(403, "Неверный секрет webhook.")
    try:
        update = Update.model_validate(
            await request.json(), context={"bot": app.state.bot}
        )
    except (ValidationError, json.JSONDecodeError):
        raise HTTPException(400, "Некорректное обновление Telegram.")
    # One process, bounded in-memory deduplication. Sleep/restart clears it.
    async with app.state.webhook_lock:
        seen = app.state.processed_updates
        now = time.monotonic()
        for key in list(seen):
            if now - seen[key] > 3600:
                del seen[key]
        if update.update_id in seen:
            return {"ok": True}
        try:
            await asyncio.wait_for(
                app.state.dispatcher.feed_update(app.state.bot, update), timeout=45
            )
        except Exception:
            logger.warning("Telegram update delivery failed; Telegram may retry")
            raise HTTPException(503, "Обработка не завершена. Повторите доставку.")
        seen[update.update_id] = now
        if len(seen) > 2000:
            del seen[next(iter(seen))]
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
@app.get("/configurator")
@app.get("/catalog")
@app.get("/compare")
@app.get("/smart")
@app.get("/saved")
@app.get("/about")
async def page():
    return FileResponse(STATIC / "index.html")
