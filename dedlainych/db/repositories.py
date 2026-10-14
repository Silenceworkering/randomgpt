import hashlib
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from dedlainych.db.models import (
    Attachment,
    Completion,
    ConnectedChat,
    Homework,
    ProcessingLog,
    Source,
    Subject,
    User,
    UserSettings,
)
from dedlainych.services.ai import Analyzer


async def register(session: AsyncSession, user_id: int, group: str) -> UserSettings:
    user = await session.get(User, user_id)
    if not user:
        session.add(User(id=user_id, group_code=group))
        await session.flush()
        session.add(UserSettings(user_id=user_id))
        await session.flush()
    return await session.get(UserSettings, user_id)


async def preferences(session: AsyncSession, user_id: int, **values) -> UserSettings:
    allowed = {"subgroup", "notify_time", "timezone", "enabled", "urgent_enabled", "registered"}
    if set(values) - allowed:
        raise ValueError("Неизвестная настройка")
    if "subgroup" in values and values["subgroup"] not in {1, 2}:
        raise ValueError("Выбери 1 или 2")
    if "timezone" in values:
        ZoneInfo(values["timezone"])
    if "notify_time" in values and not isinstance(values["notify_time"], time):
        raise ValueError("Время должно иметь формат ЧЧ:ММ")
    row = await session.get(UserSettings, user_id)
    if row is None:
        raise ValueError("Сначала /start")
    for key, value in values.items():
        setattr(row, key, value)
    await session.flush()
    return row


async def visible_homework(session: AsyncSession, user_id: int, *, include_pending: bool = False):
    user = await session.get(User, user_id)
    prefs = await session.get(UserSettings, user_id)
    if not user or not prefs:
        return []
    query = select(Homework).where(
        Homework.group_code == user.group_code,
        Homework.subgroup.in_([0, prefs.subgroup]),
        Homework.status.in_(["approved", "pending"] if include_pending else ["approved"]),
    )
    return list((await session.scalars(query.order_by(Homework.created_at.desc(), Homework.id.desc()))).all())


async def accessible(session: AsyncSession, user_id: int, homework_id: int) -> Homework | None:
    user = await session.get(User, user_id)
    prefs = await session.get(UserSettings, user_id)
    row = await session.get(Homework, homework_id)
    if not row or not user or not prefs or row.group_code != user.group_code:
        return None
    if row.status != "approved" or row.subgroup not in {0, prefs.subgroup}:
        return None
    return row


async def toggle_completion(session: AsyncSession, user_id: int, homework_id: int) -> bool:
    if not await accessible(session, user_id, homework_id):
        raise PermissionError("Задание недоступно")
    row = await session.get(Completion, (user_id, homework_id))
    if row:
        await session.delete(row)
        return False
    session.add(Completion(user_id=user_id, homework_id=homework_id))
    return True


async def ingest(
    session: AsyncSession,
    analyzer: Analyzer,
    chat_id: int,
    message_id: int,
    text: str,
    attachments: list[dict],
    today: date,
    link: str | None = None,
) -> list[Homework]:
    chat = await session.get(ConnectedChat, chat_id)
    if not chat:
        return []
    subjects = list(
        (await session.scalars(select(Subject).where(Subject.group_code == chat.group_code))).all()
    )
    previous = (
        await session.scalars(
            select(Source.text)
            .where(Source.chat_id == chat_id, Source.message_id < message_id)
            .order_by(Source.message_id.desc())
            .limit(3)
        )
    ).all()
    tasks = await analyzer.extract(
        text, {s.name: s.aliases for s in subjects}, today, context="\n".join(reversed(previous))[:4000]
    )
    source = await session.scalar(
        select(Source).where(Source.chat_id == chat_id, Source.message_id == message_id)
    )
    if not tasks and not attachments and not source:
        return []  # ordinary conversations are never stored
    if source is None:
        source = Source(chat_id=chat_id, message_id=message_id, text=text, link=link)
        session.add(source)
        await session.flush()
    elif source.text == text:
        # Album messages have distinct message IDs; redelivery is idempotent.
        return []
    else:
        source.text = text
        # Do not erase student completion on message edits; old revisions stay in archive for admins.
        for row in (await session.scalars(select(Homework).where(Homework.source_id == source.id))).all():
            row.status = "superseded"
    existing = set(
        (await session.scalars(select(Attachment.file_id).where(Attachment.source_id == source.id))).all()
    )
    for attachment in attachments:
        if attachment["file_id"] not in existing:
            session.add(Attachment(source_id=source.id, **attachment))
    if not tasks and attachments:
        from dedlainych.services.ai import ExtractedTask

        tasks = [ExtractedTask(description="Вложение требует проверки администратором", confidence=0)]
    created = []
    for task in tasks:
        subject = next((s for s in subjects if s.name == task.subject), None)
        payload = (
            f"{subject.id if subject else 0}|{task.description.lower().strip()}|{task.due}|{task.subgroup}"
        )
        fingerprint = hashlib.sha256(payload.encode()).hexdigest()
        duplicate = await session.scalar(
            select(Homework.id).where(
                Homework.group_code == chat.group_code,
                Homework.fingerprint == fingerprint,
                Homework.status.in_(["approved", "pending"]),
            )
        )
        if duplicate:
            continue
        row = Homework(
            group_code=chat.group_code,
            subject_id=subject.id if subject else None,
            source_id=source.id,
            description=task.description,
            due=task.due,
            subgroup=task.subgroup,
            status="approved" if subject and task.confidence >= 0.8 else "pending",
            fingerprint=fingerprint,
        )
        session.add(row)
        created.append(row)
    session.add(ProcessingLog(source_id=source.id, provider=analyzer.last_provider, count=len(created)))
    await session.flush()
    return created


def local_today(timezone: str) -> date:
    return datetime.now(ZoneInfo(timezone)).date()


async def completed_ids(session: AsyncSession, user_id: int) -> set[int]:
    return set(
        (await session.scalars(select(Completion.homework_id).where(Completion.user_id == user_id))).all()
    )


async def purge_completion(session: AsyncSession, homework_id: int):
    await session.execute(delete(Completion).where(Completion.homework_id == homework_id))
