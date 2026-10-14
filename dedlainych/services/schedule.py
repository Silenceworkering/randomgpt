import json
from datetime import date, time, timedelta

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from dedlainych.db.models import Lesson, Schedule, Subject


class LessonInput(BaseModel):
    date: date
    week: int | None = Field(default=None, ge=1, le=53)
    start: time
    end: time
    subject: str = Field(min_length=1, max_length=200)
    teacher: str = Field(default="", max_length=200)
    room: str = Field(default="", max_length=100)
    subgroup: int = Field(default=0, ge=0, le=2)
    cancelled: bool = False
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def chronological(self):
        if self.end <= self.start:
            raise ValueError("Конец пары должен быть позже начала")
        return self


async def import_schedule(session: AsyncSession, group: str, data: bytes) -> int:
    if len(data) > 1_000_000:
        raise ValueError("Импорт больше 1 МБ")
    raw = json.loads(data)
    if not isinstance(raw, list) or not 1 <= len(raw) <= 5000:
        raise ValueError("Ожидается массив от 1 до 5000 занятий")
    rows = [LessonInput.model_validate(item) for item in raw]
    keys = [(r.date, r.start, r.subject, r.subgroup) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Повторяющиеся занятия в импорте")
    schedule = Schedule(group_code=group)
    session.add(schedule)
    await session.flush()
    # Replace only the imported date interval, without touching homework.
    await session.execute(
        delete(Lesson).where(
            Lesson.group_code == group,
            Lesson.date >= min(r.date for r in rows),
            Lesson.date <= max(r.date for r in rows),
        )
    )
    for row in rows:
        subject = await session.scalar(
            select(Subject).where(Subject.group_code == group, Subject.name == row.subject)
        )
        if not subject:
            subject = Subject(group_code=group, name=row.subject, aliases=[])
            session.add(subject)
            await session.flush()
        session.add(
            Lesson(
                schedule_id=schedule.id,
                group_code=group,
                subject_id=subject.id,
                **row.model_dump(exclude={"subject"}),
            )
        )
    await session.flush()
    return len(rows)


async def lessons_on(session: AsyncSession, group: str, subgroup: int, day: date):
    return list(
        (
            await session.scalars(
                select(Lesson)
                .where(
                    Lesson.group_code == group,
                    Lesson.subgroup.in_([0, subgroup]),
                    Lesson.date == day,
                    Lesson.cancelled.is_(False),
                )
                .order_by(Lesson.start)
            )
        ).all()
    )


async def next_day(session: AsyncSession, group: str, subgroup: int, start: date) -> date | None:
    return await session.scalar(
        select(Lesson.date)
        .where(
            Lesson.group_code == group,
            Lesson.subgroup.in_([0, subgroup]),
            Lesson.date >= start,
            Lesson.date <= start + timedelta(days=120),
            Lesson.cancelled.is_(False),
        )
        .order_by(Lesson.date)
        .limit(1)
    )
