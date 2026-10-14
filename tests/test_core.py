import io
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from docx import Document
from PIL import Image
from pypdf import PdfWriter
from sqlalchemy import select

from dedlainych.config import Settings
from dedlainych.db.models import Attachment, Homework, NotificationHistory, Source, UserSettings
from dedlainych.db.repositories import accessible, ingest, preferences, register, toggle_completion
from dedlainych.services.admin import is_admin
from dedlainych.services.ai import Analyzer, deadline
from dedlainych.services.attachments import extract_sync
from dedlainych.services.homework import summary
from dedlainych.services.notifications import Notifier
from dedlainych.services.schedule import import_schedule, lessons_on, next_day

TODAY = date(2026, 10, 14)
SUBJECTS = {"Математика": ["матеша", "матеше"], "История": ["истории"]}
CONFIG = Settings(_env_file=None)
TEXT = "По матеше к пятнице решить №5–10, а по истории таблицу доделать"


@pytest.mark.parametrize("text", ["Всем привет", "Пойдём гулять", "Спасибо!", "Сегодня хороший день"])
def test_not_homework(text):
    assert Analyzer.rules(text, SUBJECTS, TODAY) == []


def test_multiple_tasks_and_missing_deadline():
    rows = Analyzer.rules(TEXT, SUBJECTS, TODAY)
    assert [r.subject for r in rows] == ["Математика", "История"]
    assert rows[0].due == date(2026, 10, 16)
    assert rows[1].due is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("сдать завтра", TODAY + timedelta(days=1)),
        ("к пятнице", date(2026, 10, 16)),
        ("до 16.10.2026", date(2026, 10, 16)),
        ("решить номера", None),
        ("сдать послезавтра", TODAY + timedelta(days=2)),
        ("сдать сегодня", TODAY),
    ],
)
def test_deadline(text, expected):
    assert deadline(text, TODAY) == expected


def test_unknown_and_correction():
    assert Analyzer.rules("Сделать таблицу", {}, TODAY)[0].subject is None
    assert Analyzer.rules("По матеше исправление: решить №7 вместо №5", SUBJECTS, TODAY)[0].confidence < 0.8
    assert Analyzer.rules("По матеше решить №5 подгруппа 2", SUBJECTS, TODAY)[0].subgroup == 2


async def test_rules_fallback():
    analyzer = Analyzer(Settings(_env_file=None, ai_provider="ollama"))
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=ValueError("invalid JSON"))):
        tasks = await analyzer.extract(TEXT, SUBJECTS, TODAY)
    assert len(tasks) == 2
    assert analyzer.last_provider == "rules"


async def test_llm_structured_and_no_invented_subject():
    analyzer = Analyzer(Settings(_env_file=None, ai_provider="ollama"))
    response = type(
        "Response",
        (),
        {
            "raise_for_status": lambda self: None,
            "json": lambda self: {
                "response": '{"tasks":[{"subject":"Вымысел","description":"Решить №5","due":"2026-10-17","confidence":0.99}]}'
            },
        },
    )()
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=response)):
        tasks = await analyzer.extract("Решить №5", SUBJECTS, TODAY)
    assert tasks[0].subject is None and tasks[0].due is None
    assert analyzer.last_provider == "ollama"


async def test_registration_settings_persist(database):
    async with database() as s:
        prefs = await register(s, 101, "6104-ОБ")
        await preferences(
            s, 101, subgroup=2, notify_time=time(20, 30), timezone="Europe/Moscow", registered=True
        )
        await s.commit()
        assert prefs.subgroup == 2
    async with database() as s:
        prefs = await s.get(UserSettings, 101)
        assert prefs.notify_time == time(20, 30) and prefs.registered
        with pytest.raises(ValueError):
            await preferences(s, 101, subgroup=3)


async def add_tasks(s, text=TEXT, message_id=1, files=None):
    return await ingest(s, Analyzer(CONFIG), -100123, message_id, text, files or [], TODAY)


async def test_ingestion_duplicates_edits_and_completion(database):
    async with database() as s:
        assert await ingest(s, Analyzer(CONFIG), -900, 1, TEXT, [], TODAY) == []
        assert await add_tasks(s, "Всем привет") == []
        assert await s.scalar(select(Source)) is None
        rows = await add_tasks(s)
        assert len(rows) == 2 and rows[0].status == "approved"
        first_id = rows[0].id
        assert await add_tasks(s) == []
        assert await add_tasks(s, message_id=2) == []
        await toggle_completion(s, 101, first_id)
        await s.commit()
    async with database() as s:
        assert await toggle_completion(s, 102, first_id) is True
        assert await toggle_completion(s, 101, first_id) is False
        with pytest.raises(PermissionError):
            await toggle_completion(s, 103, first_id)
        rows = await add_tasks(s, "По матеше решить №99", message_id=1)
        assert len(rows) == 1
        old = await s.get(Homework, first_id)
        assert old.status == "superseded"
        await s.commit()


async def test_attachments_preserved_pending(database):
    async with database() as s:
        rows = await add_tasks(s, "", files=[{"file_id": "telegram-file", "kind": "photo", "name": "x.jpg"}])
        assert rows[0].status == "pending"
        assert (await s.scalar(select(Attachment))).file_id == "telegram-file"
        assert await accessible(s, 101, rows[0].id) is None


def schedule_payload():
    return b'[{"date":"2026-10-16","week":7,"start":"08:15","end":"09:45","subject":"Math","subgroup":2}]'


async def test_schedule_subgroups_reimport_and_summary(database):
    async with database() as s:
        await import_schedule(s, "6104-ОБ", schedule_payload())
        assert not await lessons_on(s, "6104-ОБ", 1, date(2026, 10, 16))
        assert len(await lessons_on(s, "6104-ОБ", 2, date(2026, 10, 16))) == 1
        assert await next_day(s, "6104-ОБ", 2, TODAY) == date(2026, 10, 16)
        await preferences(s, 101, subgroup=2)
        # Explicit due date appears even when subject has no lesson on the target day.
        await add_tasks(s)
        text, tasks = await summary(s, 101, TODAY)
        assert "16.10.2026" in text and "№5" in text and len(tasks) == 1
        await import_schedule(s, "6104-ОБ", schedule_payload())
        assert len(await lessons_on(s, "6104-ОБ", 2, date(2026, 10, 16))) == 1
        assert await s.scalar(select(Homework.id))
        await s.commit()


async def test_no_schedule(database):
    async with database() as s:
        text, tasks = await summary(s, 101, TODAY)
        assert "не загружено" in text and tasks == []


async def test_notifications_restart_individual_time(database):
    bot = type("Bot", (), {"send_message": AsyncMock()})()
    async with database() as s:
        await preferences(s, 101, registered=True, notify_time=time(19), timezone="Asia/Yakutsk")
        await preferences(s, 102, registered=True, notify_time=time(22), timezone="Asia/Yakutsk")
        await preferences(s, 103, registered=True, enabled=False)
        await s.commit()
    now = datetime(2026, 10, 14, 11, 0, tzinfo=timezone.utc)  # 20:00 Yakutsk
    await Notifier(database, bot).tick(now)
    assert bot.send_message.await_count == 1
    assert bot.send_message.call_args.args[0] == 101
    await Notifier(database, bot).tick(now)
    assert bot.send_message.await_count == 1
    async with database() as s:
        assert (await s.get(NotificationHistory, (101, TODAY, "daily"))).status == "sent"


@pytest.mark.parametrize(("uid", "expected"), [(1, True), (2, False)])
def test_admin(uid, expected):
    assert is_admin(uid, Settings(_env_file=None, admin_ids=[1])) == expected


def test_documents():
    document = Document()
    document.add_paragraph("Решить №5")
    stream = io.BytesIO()
    document.save(stream)
    assert "Решить" in extract_sync(stream.getvalue(), "hw.docx", 1000000)
    assert extract_sync("Привет".encode(), "hw.txt", 1000) == "Привет"
    pdf = PdfWriter()
    pdf.add_blank_page(width=100, height=100)
    stream = io.BytesIO()
    pdf.write(stream)
    assert extract_sync(stream.getvalue(), "hw.pdf", 1000000) == ""


def test_ocr_path():
    stream = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(stream, "PNG")
    with patch("pytesseract.image_to_string", return_value="Решить №5") as ocr:
        assert extract_sync(stream.getvalue(), "hw.png", 100000) == "Решить №5"
        assert ocr.call_args.kwargs["lang"] == "rus+eng"


@pytest.mark.parametrize(
    ("data", "filename", "limit"),
    [(b"x" * 100, "hw.txt", 10), (b"MZ", "evil.exe", 100), (b"fake", "hw.pdf", 100)],
)
def test_unsafe_files(data, filename, limit):
    with pytest.raises(ValueError):
        extract_sync(data, filename, limit)


async def test_import_validation(database):
    async with database() as s:
        with pytest.raises(ValueError):
            await import_schedule(
                s, "6104-ОБ", b'[{"date":"2026-10-16","start":"09:00","end":"08:00","subject":"Math"}]'
            )


async def test_subgroup_visibility(database):
    async with database() as s:
        rows = await add_tasks(s, "По матеше решить №5 подгруппа 2")
        assert await accessible(s, 101, rows[0].id) is None
        await preferences(s, 101, subgroup=2)
        assert await accessible(s, 101, rows[0].id) is rows[0]


async def test_single_scheduler_postgres_lock(database):
    from dedlainych.services.notifications import scheduler_lock

    async with database() as s:
        engine = s.bind
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL advisory lock integration test")
    first = await scheduler_lock(engine)
    try:
        with pytest.raises(RuntimeError):
            await scheduler_lock(engine)
    finally:
        # Session-level lock survives return to SQLAlchemy pool: explicitly unlock before fixture cleanup.
        from sqlalchemy import text

        await first.execute(text("SELECT pg_advisory_unlock_all()"))
        await first.close()
