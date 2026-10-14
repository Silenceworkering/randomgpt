"""Durable receipt before webhook acknowledgement; processing is separate from HTTP latency."""

import logging
from datetime import timedelta

from aiogram.types import Update
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from dedlainych.db.models import TelegramInbox, utcnow

log = logging.getLogger(__name__)


async def enqueue(sessions, update: Update) -> bool:
    try:
        async with sessions() as session:
            session.add(
                TelegramInbox(
                    update_id=update.update_id,
                    payload=update.model_dump(mode="json", by_alias=True, exclude_none=True),
                )
            )
            await session.commit()
        return True
    except IntegrityError:
        return False


async def drain(sessions, bot, dispatcher, limit: int = 25) -> int:
    handled = 0
    for _ in range(limit):
        async with sessions() as session, session.begin():
            # PostgreSQL locks survive until the handler and inbox result are committed.
            # A second Render instance or notification job skips rows already being processed.
            row = await session.scalar(
                select(TelegramInbox)
                .where(TelegramInbox.status == "pending", TelegramInbox.available_at <= utcnow())
                .order_by(TelegramInbox.update_id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                break
            try:
                update = Update.model_validate(row.payload, context={"bot": bot})
                await dispatcher.feed_update(bot, update)
            except Exception as exc:
                row.attempts += 1
                row.available_at = utcnow() + timedelta(minutes=2)
                log.warning("Повтор обработки webhook; тип ошибки: %s", type(exc).__name__)
                if row.attempts >= 5:
                    row.status, row.payload = "failed", {}
                    row.processed_at = utcnow()
            else:
                row.status, row.payload = "processed", {}
                row.processed_at = utcnow()
            handled += 1
    async with sessions() as session:
        await session.execute(
            delete(TelegramInbox).where(
                TelegramInbox.status.in_(["processed", "failed"]),
                TelegramInbox.processed_at < utcnow() - timedelta(days=7),
            )
        )
        await session.commit()
    return handled
