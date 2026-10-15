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
