"""Only explicit admin confirmation may replace or cancel an existing assignment."""

import hashlib
import json
import re

from sqlalchemy import select

from dedlainych.db.models import Homework, Source


def revision_token(row: Homework) -> str:
    content = [row.subject_id, row.description, str(row.due), row.subgroup, row.status]
    return hashlib.sha256(json.dumps(content, ensure_ascii=False).encode()).hexdigest()


async def bind_target(session, proposal: Homework, target: Homework):
    if proposal.id == target.id or proposal.group_code != target.group_code or target.status != "approved":
        raise ValueError("Нужно действующее подтверждённое задание той же группы")
    source = await session.get(Source, proposal.source_id)
    original = await session.get(Source, target.source_id)
    if source.chat_id != original.chat_id:
        raise ValueError("Исправление должно относиться к тому же чату")
    proposal.target_id, proposal.target_fingerprint = target.id, revision_token(target)
    fields = proposal.changes.get("change_fields", [])
    proposal.subject_id = target.subject_id
    if "due" not in fields:
        proposal.due = target.due
    if "subgroup" not in fields:
        proposal.subgroup = target.subgroup
    if "description" not in fields:
        proposal.description = target.description
    else:
        text = proposal.changes.get("description", proposal.description)
        replacement = re.search(
            r"вместо\s+№?\s*(\d+)\s+(?:делаем\s+|решаем\s+|номер\s+|№\s*)?(\d+)", text, re.I
        )
        if replacement and re.search(r"(?<!\d)" + replacement[1] + r"(?!\d)", target.description):
            proposal.description = re.sub(
                r"(?<!\d)" + replacement[1] + r"(?!\d)", replacement[2], target.description
            )
        else:
            proposal.description = text
    # Carry original materials without removing the original Telegram file_ids.
    from dedlainych.db.models import Attachment

    originals = (
        await session.scalars(select(Attachment).where(Attachment.source_id == target.source_id))
    ).all()
    existing = set(
        (
            await session.scalars(
                select(Attachment.file_id).where(Attachment.source_id == proposal.source_id)
            )
        ).all()
    )
    for item in originals:
        if item.file_id not in existing:
            session.add(
                Attachment(source_id=proposal.source_id, file_id=item.file_id, kind=item.kind, name=item.name)
            )
            existing.add(item.file_id)


async def approve(session, homework_id: int, group: str):
    row = await session.scalar(select(Homework).where(Homework.id == homework_id).with_for_update())
    if row is None or row.group_code != group:
        raise PermissionError("Задание недоступно")
    if row.status == "approved":
        return  # idempotent callback replay
    if row.status != "pending":
        raise ValueError("Предложение уже обработано")
    if row.operation != "create":
        target = await session.scalar(select(Homework).where(Homework.id == row.target_id).with_for_update())
        if target is None:
            raise ValueError(f"Укажи исходное задание: /admin target {row.id} ID")
        if (
            target.group_code != group
            or target.status != "approved"
            or revision_token(target) != row.target_fingerprint
        ):
            raise ValueError("Исходное задание изменилось. Проверь предложение и назначь target заново")
        if row.operation == "cancel":
            target.status = "rejected"
            row.status = "rejected"
            await session.flush()
            return
    if not row.subject_id:
        raise ValueError(f"Сначала назначь предмет: /admin subject {row.id} Название")
    if row.operation != "create":
        target.status = "superseded"
    row.status = "approved"
    await session.flush()
