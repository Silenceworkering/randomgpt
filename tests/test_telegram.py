from datetime import datetime, timezone
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Chat, Message, User

from dedlainych.config import Settings
from dedlainych.db.models import UserSettings
from dedlainych.telegram.handlers import UI
from dedlainych.telegram.keyboards import menu


async def test_start_and_onboarding(database):
    ui = UI(database, Settings(_env_file=None))
    message = Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=501, type="private"),
        from_user=User(id=501, is_bot=False, first_name="Student"),
        text="/start",
    )
    # Actual handler executes with a mocked Telegram transport; database is real.
    message = type("Incoming", (), {"from_user": message.from_user, "answer": AsyncMock()})()
    await ui.start(message)
    assert "Дедлайныч" in message.answer.call_args.args[0]
    async with database() as s:
        assert await s.get(UserSettings, 501)


async def test_foreign_callback_denied(database):
    ui = UI(database, Settings(_env_file=None))
    cb = type(
        "Callback",
        (),
        {
            "from_user": type("U", (), {"id": 103})(),
            "data": "toggle:999",
            "message": None,
            "answer": AsyncMock(),
        },
    )()
    await ui.callback(cb)
    assert cb.answer.call_args.kwargs["show_alert"]


def test_menu_actions():
    actions = {b.callback_data for row in menu(True).inline_keyboard for b in row}
    assert {
        "now",
        "tomorrow",
        "archive:0",
        "progress",
        "notifications",
        "settings",
        "help",
        "admin",
    } <= actions


def test_html_limit_keeps_entities_and_tags():
    from dedlainych.telegram.render import limit_html

    result = limit_html("<b>" + "&lt;" * 2000 + "</b>")
    assert len(result) <= 4000
    assert "</b>" in result
    assert not result.split("</b>")[0].endswith("&l")


async def test_actual_now_handler_uses_database(database):
    from unittest.mock import patch
    from dedlainych.db.repositories import preferences

    ui = UI(database, Settings(_env_file=None))
    message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=101, type="private"))
    cb = CallbackQuery(
        id="q",
        from_user=User(id=101, is_bot=False, first_name="Student"),
        chat_instance="instance",
        message=message,
        data="now",
    )
    async with database() as s:
        prefs = await preferences(s, 101, registered=True)
        with patch("dedlainych.telegram.handlers.edit", new=AsyncMock()) as output:
            await ui.section(s, cb, 101, "now", prefs)
            assert "не загружено" in output.call_args.args[1]


async def test_admin_callback_rejects_normal_user(database):
    import pytest

    ui = UI(database, Settings(_env_file=None, admin_ids=[999]))
    async with database() as s:
        with pytest.raises(PermissionError):
            await ui.admin_callback(s, None, 101, "approve:1", "6104-ОБ")


async def test_prompt_and_urgent_callbacks_respect_access(database):
    import pytest
    from unittest.mock import patch
    from dedlainych.db.repositories import ingest, preferences
    from dedlainych.services.ai import Analyzer

    ui = UI(database, Settings(_env_file=None))
    async with database() as session:
        h = (
            await ingest(
                session,
                Analyzer(ui.config),
                -100123,
                71,
                "По матеше решить №5 до завтра",
                [],
                datetime.now(timezone.utc).date(),
            )
        )[0]
        prefs = await preferences(session, 101, registered=True)
        with patch("dedlainych.telegram.handlers.edit", new=AsyncMock()) as output:
            await ui.section(session, None, 101, f"prompt:{h.id}", prefs)
            assert "№5" in output.call_args.args[1]
            assert "CHATGPT" in output.call_args.args[1]
            for row in output.call_args.args[2].inline_keyboard:
                for button in row:
                    if button.copy_text:
                        assert 1 <= len(button.copy_text.text) <= 256
            await ui.section(session, None, 101, "urgent", prefs)
            assert "№5" in output.call_args.args[1]
        foreign = await session.get(UserSettings, 103)
        with pytest.raises(PermissionError):
            await ui.section(session, None, 103, f"prompt:{h.id}", foreign)


async def test_group_failure_remains_in_durable_queue(database):
    from unittest.mock import patch
    from aiogram import Bot
    from aiogram.types import Update
    from dedlainych.services.inbox import enqueue, drain
    from dedlainych.telegram.dispatcher import build_dispatcher

    event = Update(
        update_id=9701,
        message=Message(
            message_id=33,
            date=datetime.now(timezone.utc),
            chat=Chat(id=-100123, type="supergroup"),
            text="Синтетическое сообщение",
            from_user=User(id=101, first_name="Student", is_bot=False),
        ),
    )
    bot = Bot("123456789:TEST_NOT_A_REAL_TOKEN")
    try:
        assert await enqueue(database, event)
        with patch(
            "dedlainych.telegram.handlers.ingest",
            new=AsyncMock(side_effect=RuntimeError("database temporarily unavailable")),
        ):
            await drain(database, bot, build_dispatcher(database, Settings(_env_file=None)))
        from dedlainych.db.models import TelegramInbox

        async with database() as session:
            row = await session.get(TelegramInbox, 9701)
            assert row.status == "pending" and row.attempts == 1
    finally:
        await bot.session.close()


async def test_full_prompt_document_keeps_entire_task(database):
    from types import SimpleNamespace
    from dedlainych.db.repositories import ingest
    from dedlainych.services.ai import Analyzer

    ui = UI(database, Settings(_env_file=None))
    async with database() as session:
        task = (
            await ingest(
                session,
                Analyzer(ui.config),
                -100123,
                72,
                "По матеше решить №5",
                [],
                datetime.now(timezone.utc).date(),
            )
        )[0]
        task.description = "Условие " * 200 + "ОБЯЗАТЕЛЬНОЕ ПОСЛЕДНЕЕ УСЛОВИЕ"
        cb = SimpleNamespace(message=SimpleNamespace(answer_document=AsyncMock()))
        await ui.section(session, cb, 101, f"promptfile:{task.id}", await session.get(UserSettings, 101))
        document = cb.message.answer_document.call_args.args[0]
        assert document.data.decode().endswith("ОБЯЗАТЕЛЬНОЕ ПОСЛЕДНЕЕ УСЛОВИЕ")
