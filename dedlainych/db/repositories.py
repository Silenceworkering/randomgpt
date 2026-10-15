import hashlib
import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from dedlainych.db.models import (
    Attachment,
    ChatContext,
    utcnow,
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


async def set_completion(session: AsyncSession, user_id: int, homework_id: int, done: bool) -> None:
    if not await accessible(session, user_id, homework_id):
        raise PermissionError("Задание недоступно")
    row = await session.get(Completion, (user_id, homework_id))
    if done and row is None:
        session.add(Completion(user_id=user_id, homework_id=homework_id))
    elif not done and row is not None:
        await session.delete(row)
    await session.flush()


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def purge_context(session: AsyncSession):
    await session.execute(
        delete(ChatContext)
        .where(ChatContext.expires_at <= utcnow())
        .execution_options(synchronize_session="fetch")
    )


async def ingest(
    session: AsyncSession,
    analyzer: Analyzer,
    chat_id: int,
    message_id: int,
    text: str,
    attachments: list[dict],
    today: date,
    link: str | None = None,
    received_at: datetime | None = None,
    *,
    version_at: datetime | None = None,
    reply_to_message_id: int | None = None,
    reply_text: str = "",
    forwarded: bool = False,
) -> list[Homework]:
    from dedlainych.services.ai import ExtractedTask, subject_matches
    from dedlainych.services.ai_budget import reserve_call
    from dedlainych.services.revisions import bind_target

    chat = await session.scalar(select(ConnectedChat).where(ConnectedChat.id == chat_id).with_for_update())
    if not chat:
        return []
    now = utcnow()
    version = aware(version_at or received_at or now)
    content_hash = hashlib.sha256(
        json.dumps(
            [text, sorted(a["file_id"] for a in attachments), reply_to_message_id, forwarded],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    source = await session.scalar(
        select(Source).where(Source.chat_id == chat_id, Source.message_id == message_id)
    )
    if source is not None and not source.content_hash and source.text == text:
        # Rows created before this migration already represent processed messages.
        known_files = set(
            (await session.scalars(select(Attachment.file_id).where(Attachment.source_id == source.id))).all()
        )
        if all(a["file_id"] in known_files for a in attachments):
            source.content_hash, source.version_at = content_hash, version
            return []
    cached = await session.get(ChatContext, (chat_id, message_id))
    # Deduplicate before inference and quota reservation, including message edits.
    for previous in [source, cached]:
        if previous is not None:
            if previous.content_hash == content_hash:
                return []
            if previous.version_at and aware(previous.version_at) > version:
                return []  # delayed old update must not undo a newer edit
    subjects = list(
        (await session.scalars(select(Subject).where(Subject.group_code == chat.group_code))).all()
    )
    previous = list(
        (
            await session.scalars(
                select(ChatContext)
                .where(
                    ChatContext.chat_id == chat_id,
                    ChatContext.message_id < message_id,
                    ChatContext.version_at <= version,
                    ChatContext.expires_at > now,
                    ChatContext.version_at
                    >= version - timedelta(minutes=analyzer.config.context_ttl_minutes),
                )
                .order_by(ChatContext.message_id.desc())
                .limit(analyzer.config.context_message_limit)
            )
        ).all()
    )
    messages = [dict(message_id=r.message_id, text=r.text) for r in reversed(previous)]
    # Reply text is untrusted context; use only while the original Telegram date is
    # fresh (handler enforces this), and never persist sender identities.
    if reply_to_message_id and reply_text:
        messages = [m for m in messages if m["message_id"] != reply_to_message_id]
        messages.append(dict(message_id=reply_to_message_id, text=reply_text[:2000]))
    context_ids = [m["message_id"] for m in messages]
    targets = list(
        (
            await session.scalars(
                select(Homework)
                .join(Source, Homework.source_id == Source.id)
                .where(
                    Source.chat_id == chat_id,
                    Source.message_id.in_(context_ids + ([message_id] if source else [])),
                    Homework.status == "approved",
                )
                .order_by(Homework.id.desc())
            )
        ).all()
    )
    from dedlainych.services.schedule import lessons_on

    names = {s.id: s.name for s in subjects}
    tomorrow_subjects = []
    for subgroup in (1, 2):
        for lesson in await lessons_on(session, chat.group_code, subgroup, today + timedelta(days=1)):
            hint = dict(subject=names.get(lesson.subject_id), subgroup=subgroup)
            if hint not in tomorrow_subjects:
                tomorrow_subjects.append(hint)
    context = json.dumps(
        dict(
            messages=messages,
            assignments=[
                dict(
                    message_id=(await session.get(Source, h.source_id)).message_id,
                    subject_id=h.subject_id,
                    description=h.description[:500],
                    due=str(h.due),
                    subgroup=h.subgroup,
                )
                for h in targets
            ],
            forwarded=forwarded,
            tomorrow_subjects=tomorrow_subjects,
        ),
        ensure_ascii=False,
    )
    # Keep recent context first; do not truncate a JSON object in the middle.
    packed = json.loads(context)
    for message in packed["messages"]:
        message["text"] = message["text"][:1000]
    while len(json.dumps(packed, ensure_ascii=False)) > 5500 and len(packed["messages"]) > 1:
        packed["messages"].pop(0)
    packed["assignments"] = packed["assignments"][:5]
    context = json.dumps(packed, ensure_ascii=False)
    # Separate instance prevents provider/result metadata crossing concurrent chats.
    tasks = await analyzer.extract(
        text,
        {s.name: s.aliases for s in subjects},
        today,
        context=context,
        reserve=lambda: reserve_call(session.bind, analyzer.config.ai_daily_request_limit),
    )
    if cached is not None and aware(cached.expires_at) <= now:
        cached = None
    await purge_context(session)
    if version + timedelta(minutes=analyzer.config.context_ttl_minutes) > now:
        if cached is None:
            cached = ChatContext(chat_id=chat_id, message_id=message_id)
            session.add(cached)
        cached.text, cached.version_at, cached.content_hash = text[:2000], version, content_hash
        cached.expires_at = version + timedelta(minutes=analyzer.config.context_ttl_minutes)
        await session.flush()
        keep = (
            select(ChatContext.message_id)
            .where(ChatContext.chat_id == chat_id)
            .order_by(ChatContext.message_id.desc())
            .limit(analyzer.config.context_message_limit)
        )
        await session.execute(
            delete(ChatContext).where(ChatContext.chat_id == chat_id, ChatContext.message_id.not_in(keep))
        )
    if not tasks and not attachments and not source:
        logging.getLogger(__name__).info(
            "analysis_result provider=%s reason=%s created=0 pending=0",
            analyzer.last_provider,
            analyzer.last_reason,
        )
        return []
    edited = source is not None
    if source is None:
        source = Source(
            chat_id=chat_id, message_id=message_id, text=text, link=link, received_at=received_at or now
        )
        session.add(source)
        await session.flush()
    source.text, source.version_at, source.content_hash = text, version, content_hash
    existing = set(
        (await session.scalars(select(Attachment.file_id).where(Attachment.source_id == source.id))).all()
    )
    for attachment in attachments:
        if attachment["file_id"] not in existing:
            session.add(Attachment(source_id=source.id, **attachment))
            existing.add(attachment["file_id"])
    if not tasks and (attachments or edited):
        tasks = [
            ExtractedTask(
                description=text[:2000] or "Вложение требует проверки администратором",
                confidence=0,
                operation="update" if edited else "create",
                change_fields=["description"],
                review_reason="Изменённое сообщение/вложение не распознано: проверить вручную",
            )
        ]
    created = []
    for task in tasks:
        subject = next((s for s in subjects if s.name == task.subject), None)
        operation = "update" if edited and task.operation == "create" else task.operation
        candidates = targets
        if edited:
            candidates = [h for h in candidates if h.source_id == source.id]
        elif reply_to_message_id:
            candidates = [
                h
                for h in candidates
                if (await session.get(Source, h.source_id)).message_id == reply_to_message_id
            ]
        elif task.target_message_id:
            candidates = [
                h
                for h in candidates
                if (await session.get(Source, h.source_id)).message_id == task.target_message_id
            ]
        if subject and any(
            m[2] == subject.name for m in subject_matches(text, {s.name: s.aliases for s in subjects})
        ):
            candidates = [h for h in candidates if h.subject_id == subject.id]
        target = candidates[0] if len(candidates) == 1 and operation != "create" else None
        # Inferred contextual targets are suggestions only, never immediate writes.
        payload = f"{subject.id if subject else 0}|{task.description.lower().strip()}|{task.due}|{task.subgroup}|{operation}|{target.id if target else 0}"
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
        changes = task.model_dump(mode="json")
        if edited and not changes["change_fields"]:
            changes["change_fields"] = ["description", "due", "subgroup"]
        row = Homework(
            group_code=chat.group_code,
            subject_id=subject.id if subject else None,
            source_id=source.id,
            description=task.description,
            due=task.due,
            subgroup=task.subgroup,
            fingerprint=fingerprint,
            operation=operation,
            changes=changes,
            review_reason=task.review_reason,
            status="approved"
            if subject and task.confidence >= 0.8 and operation == "create" and not forwarded
            else "pending",
        )
        session.add(row)
        await session.flush()
        if target:
            await bind_target(session, row, target)
        if operation != "create":
            row.review_reason = "Исправление/отмена: " + (
                f"исходное #{target.id}" if target else "исходное задание не определено"
            )
        if forwarded:
            row.review_reason = "Пересланное задание: проверить актуальность и срок"
        if row.status == "pending" and not row.review_reason:
            row.review_reason = "Неизвестный предмет или недостаточная уверенность"
        created.append(row)
    session.add(ProcessingLog(source_id=source.id, provider=analyzer.last_provider, count=len(created)))
    logging.getLogger(__name__).info(
        "analysis_result provider=%s reason=%s created=%d pending=%d",
        analyzer.last_provider,
        analyzer.last_reason,
        len(created),
        sum(h.status == "pending" for h in created),
    )
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
