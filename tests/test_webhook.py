import asyncio
import ssl
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer
from aiogram.types import Update

from dedlainych.config import Settings
from dedlainych.db.models import TelegramInbox, utcnow
from dedlainych.db.repositories import set_completion
from dedlainych.services.inbox import drain, enqueue
from dedlainych.webhook import build_app


def event(uid=700):
    return Update(update_id=uid)


async def test_durable_inbox_deduplicates_and_erases_processed_payload(database):
    assert await enqueue(database, event())
    assert not await enqueue(database, event())
    dispatcher = type("Dispatcher", (), {"feed_update": AsyncMock()})()
    assert await drain(database, None, dispatcher) == 1
    assert await drain(database, None, dispatcher) == 0
    assert dispatcher.feed_update.await_count == 1
    async with database() as session:
        row = await session.get(TelegramInbox, 700)
        assert row.status == "processed" and row.payload == {}
    assert not await enqueue(database, event())


async def test_pending_inbox_survives_processor_restart(database):
    await enqueue(database, event())
    first = type("Dispatcher", (), {"feed_update": AsyncMock(side_effect=RuntimeError("not logged"))})()
    await drain(database, None, first)
    async with database() as session:
        row = await session.get(TelegramInbox, 700)
        assert row.status == "pending" and row.attempts == 1
        row.available_at = utcnow()
        await session.commit()
    restarted = type("Dispatcher", (), {"feed_update": AsyncMock()})()
    assert await drain(database, None, restarted) == 1
    assert restarted.feed_update.await_count == 1


async def test_webhook_authentication_and_durable_receipt(database):
    config = Settings(_env_file=None, run_mode="webhook", webhook_secret="safe_test_header_1234")
    dispatcher = type("Dispatcher", (), {"feed_update": AsyncMock()})()
    app = build_app(config, database, None, dispatcher, manage_lifecycle=False)
    async with TestClient(TestServer(app)) as client:
        response = await client.post("/telegram/webhook", json={"update_id": 701})
        assert response.status == 403
        headers = {"X-Telegram-Bot-Api-Secret-Token": "safe_test_header_1234"}
        response = await client.post("/telegram/webhook", json={"update_id": 701}, headers=headers)
        assert response.status == 200
        response = await client.post("/telegram/webhook", json={"bad": True}, headers=headers)
        assert response.status == 400
        with patch("dedlainych.webhook.enqueue", new=AsyncMock(side_effect=ConnectionError())):
            response = await client.post("/telegram/webhook", json={"update_id": 702}, headers=headers)
            assert response.status == 503
        response = await client.get("/health")
        assert await response.json() == {"ok": True, "mode": "webhook"}
    async with database() as session:
        assert await session.get(TelegramInbox, 701)
        assert await session.get(TelegramInbox, 702) is None


async def test_two_webhook_consumers_do_not_process_same_update(database):
    async with database() as session:
        if session.bind.dialect.name != "postgresql":
            pytest.skip("PostgreSQL SKIP LOCKED integration test")
    await enqueue(database, event())

    async def feed(*args):
        await asyncio.sleep(0.1)

    dispatcher = type("Dispatcher", (), {"feed_update": AsyncMock(side_effect=feed)})()
    await asyncio.gather(drain(database, None, dispatcher), drain(database, None, dispatcher))
    assert dispatcher.feed_update.await_count == 1


def test_neon_sslmode_uses_verified_tls_and_preserves_password():
    from dedlainych.db.session import make_database

    sentinel = object()
    with patch("dedlainych.db.session.create_async_engine", return_value=sentinel) as create:
        engine, _ = make_database("postgresql://user:p%40ss@neon.example/db?sslmode=require")
        assert engine is sentinel
        url = create.call_args.args[0]
        assert url.password == "p@ss" and "sslmode" not in url.query
        context = create.call_args.kwargs["connect_args"]["ssl"]
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname


async def test_completion_intent_is_idempotent_on_webhook_replay(database):
    from dedlainych.services.ai import Analyzer
    from dedlainych.db.repositories import ingest, completed_ids

    async with database() as session:
        rows = await ingest(
            session,
            Analyzer(Settings(_env_file=None)),
            -100123,
            5,
            "По матеше решить №10",
            [],
            datetime.now(timezone.utc).date(),
        )
        hid = rows[0].id
        await set_completion(session, 101, hid, True)
        await set_completion(session, 101, hid, True)
        assert hid in await completed_ids(session, 101)
        await set_completion(session, 101, hid, False)
        await set_completion(session, 101, hid, False)
        assert hid not in await completed_ids(session, 101)


async def test_inbox_preserves_telegram_aliases_and_bot_context(database):
    from aiogram import Bot
    from aiogram.types import Message

    bot = Bot("123456:" + "x" * 35)
    try:
        message = Message.model_validate(
            {
                "message_id": 1,
                "date": 1,
                "chat": {"id": 101, "type": "private"},
                "from": {"id": 101, "is_bot": False, "first_name": "Student"},
                "text": "/start",
            }
        )
        await enqueue(database, Update(update_id=900, message=message))
        dispatcher = type("Dispatcher", (), {"feed_update": AsyncMock()})()
        await drain(database, bot, dispatcher)
        received = dispatcher.feed_update.call_args.args[1]
        assert received.message.from_user.id == 101
        assert received.message.bot is bot
    finally:
        await bot.session.close()


async def test_free_notification_settings_explain_delay(database):
    from dedlainych.telegram.handlers import UI
    from dedlainych.db.models import UserSettings

    config = Settings(_env_file=None, run_mode="webhook")
    async with database() as session:
        prefs = await session.get(UserSettings, 101)
        with patch("dedlainych.telegram.handlers.edit", new=AsyncMock()) as edit:
            await UI(database, config).section(session, None, 101, "notifications", prefs)
            assert "30 минут" in edit.call_args.args[1]


async def test_parallel_webhook_ingestion_keeps_single_homework(database):
    from dedlainych.db.repositories import ingest
    from dedlainych.services.ai import Analyzer
    from dedlainych.db.models import Homework
    from sqlalchemy import select, func

    async with database() as session:
        if session.bind.dialect.name != "postgresql":
            pytest.skip("PostgreSQL chat row lock integration test")

    async def receive(mid):
        async with database() as session:
            await ingest(
                session,
                Analyzer(Settings(_env_file=None)),
                -100123,
                mid,
                "По матеше решить №999",
                [],
                utcnow().date(),
            )
            await session.commit()

    await asyncio.gather(receive(910), receive(911))
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(Homework)) == 1


async def test_expired_callback_after_free_cold_start_still_opens_menu(database):
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import AnswerCallbackQuery
    from aiogram.types import Chat, Message, User
    from types import SimpleNamespace
    from dedlainych.telegram.handlers import UI
    from dedlainych.db.repositories import preferences

    async with database() as session:
        await preferences(session, 101, registered=True)
        await session.commit()
    callback = SimpleNamespace(
        from_user=User(id=101, is_bot=False, first_name="Student"),
        data="home",
        message=Message(message_id=1, date=utcnow(), chat=Chat(id=101, type="private")),
        answer=AsyncMock(
            side_effect=TelegramBadRequest(
                method=AnswerCallbackQuery(callback_query_id="expired"), message="query is too old"
            )
        ),
    )
    with patch("dedlainych.telegram.handlers.edit", new=AsyncMock()) as edit:
        await UI(database, Settings(_env_file=None, run_mode="webhook")).callback(callback)
        assert "ДЕДЛАЙНЫЧ" in edit.call_args.args[1]


async def test_queued_homework_uses_message_date_not_wakeup_date(database):
    from aiogram.types import Chat, Message, User
    from sqlalchemy import select
    from dedlainych.db.models import Homework, Source
    from dedlainych.telegram.handlers import UI

    sent = datetime(2026, 10, 14, 14, tzinfo=timezone.utc)
    message = Message(
        message_id=950,
        date=sent,
        chat=Chat(id=-100123, type="supergroup"),
        from_user=User(id=101, is_bot=False, first_name="Student"),
        text="По матеше решить №10 завтра",
    )
    await UI(database, Settings(_env_file=None)).group_message(message)
    async with database() as session:
        task = await session.scalar(select(Homework))
        source = await session.scalar(select(Source))
        assert task.due.isoformat() == "2026-10-15"
        assert source.received_at.replace(tzinfo=timezone.utc) == sent
