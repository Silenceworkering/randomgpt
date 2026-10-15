from datetime import date

import pytest
from sqlalchemy import select

from dedlainych.db.models import Subject, WeeklyPlan
from dedlainych.services.group_6104 import configure_week
from dedlainych.services.schedule import import_schedule, lessons_on, next_day
from dedlainych.telegram.keyboards import menu


async def names(session, subgroup, day):
    subjects = {s.id: s.name for s in (await session.scalars(select(Subject))).all()}
    return [subjects[r.subject_id] for r in await lessons_on(session, "6104-ОБ", subgroup, day)]


async def test_alternation_subgroups_and_restart(database):
    async with database() as session:
        await configure_week(session, "6104-ОБ", 1, date(2026, 10, 12))
        await session.commit()
    # A new session loads persisted configuration, as after a restart.
    async with database() as session:
        assert (await names(session, 1, date(2026, 10, 13)))[0] == "Линейная алгебра и теория матриц"
        assert (await names(session, 1, date(2026, 10, 20)))[0] == "Культурология"
        assert (await names(session, 1, date(2026, 10, 27)))[0] == "Линейная алгебра и теория матриц"
        first = await names(session, 1, date(2026, 10, 12))
        second = await names(session, 2, date(2026, 10, 12))
        assert "Основы программирования" in first
        assert "Основы программирования" not in second
        assert "Начертательная геометрия и инженерная графика" in second
        assert len(await names(session, 1, date(2026, 10, 15))) == 3
        assert len(await names(session, 2, date(2026, 10, 15))) == 4
        assert (await names(session, 1, date(2026, 10, 16)))[0] == "Цифровая грамотность"
        assert (await names(session, 2, date(2026, 10, 16)))[0] == "Иностранный язык"
        assert await next_day(session, "6104-ОБ", 2, date(2026, 10, 17)) == date(2026, 10, 19)
        assert await lessons_on(session, "other", 1, date(2026, 10, 13)) == []
        assert await lessons_on(session, "6104-ОБ", 1, date(2026, 10, 11)) == []


async def test_week_two_anchor_and_idempotence(database):
    async with database() as session:
        for _ in range(2):
            await configure_week(session, "6104-ОБ", 2, date(2026, 10, 12))
        assert (await names(session, 1, date(2026, 10, 13)))[0] == "Культурология"
        assert (await names(session, 1, date(2026, 10, 20)))[0] == "Линейная алгебра и теория матриц"
        subjects = (
            await session.scalars(select(Subject).where(Subject.name == "Основы программирования на Python"))
        ).all()
        assert len(subjects) == 1
        assert "питону" in subjects[0].aliases
        await session.delete(await session.get(WeeklyPlan, "6104-ОБ"))
        await session.flush()
        assert await lessons_on(session, "6104-ОБ", 1, date(2026, 10, 13)) == []


async def test_dated_cancel_overrides_weekly_plan(database):
    import json

    async with database() as session:
        await configure_week(session, "6104-ОБ", 1, date(2026, 10, 12))
        await import_schedule(
            session,
            "6104-ОБ",
            json.dumps(
                [
                    dict(
                        date="2026-10-13",
                        start="08:15",
                        end="09:45",
                        subject="Линейная алгебра и теория матриц",
                        cancelled=True,
                    )
                ]
            ).encode(),
        )
        assert await lessons_on(session, "6104-ОБ", 1, date(2026, 10, 13)) == []
        assert await names(session, 1, date(2026, 10, 14))


async def test_invalid_week_configuration(database):
    async with database() as session:
        for group, week, monday in [
            ("other", 1, date(2026, 10, 12)),
            ("6104-ОБ", 3, date(2026, 10, 12)),
            ("6104-ОБ", 1, date(2026, 10, 13)),
        ]:
            with pytest.raises(ValueError):
                await configure_week(session, group, week, monday)


def test_schedule_removed_from_menu():
    assert all(b.callback_data != "schedule" for row in menu().inline_keyboard for b in row)


async def test_tomorrow_summary_selects_weekly_subjects(database):
    from dedlainych.config import Settings
    from dedlainych.db.repositories import ingest, preferences
    from dedlainych.services.ai import Analyzer
    from dedlainych.services.homework import summary

    async with database() as session:
        await configure_week(session, "6104-ОБ", 1, date(2026, 10, 12))
        analyzer = Analyzer(Settings(_env_file=None))
        tasks = []
        for mid, text in enumerate(
            ["По питону решить №6", "История России: прочитать главу 3", "По культурологии сделать таблицу"],
            start=20,
        ):
            tasks.extend(await ingest(session, analyzer, -100123, mid, text, [], date(2026, 10, 14)))
        assert len(tasks) == 3
        assert all(t.status == "approved" for t in tasks)
        await preferences(session, 101, subgroup=2)
        text, selected = await summary(session, 101, date(2026, 10, 15))
        assert [t.id for t in selected] == [tasks[0].id]
        assert "№6" in text and "главу 3" not in text
        await preferences(session, 101, subgroup=1)
        _, selected = await summary(session, 101, date(2026, 10, 15))
        assert selected == []
