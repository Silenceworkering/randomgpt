import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from dedlainych.db.models import NotificationHistory, UserSettings
from dedlainych.db.repositories import completed_ids, visible_homework
from dedlainych.services.homework import summary

from dedlainych.telegram.render import limit_html

log = logging.getLogger(__name__)
LOCK_ID = 6104001


class Notifier:
    def __init__(self, sessions, bot):
        self.sessions, self.bot = sessions, bot

    async def claim(self, uid, day, kind):
        try:
            async with self.sessions() as session:
                session.add(NotificationHistory(user_id=uid, day=day, kind=kind))
                await session.commit()
            return True
        except IntegrityError:
            return False

    async def tick(self, now: datetime | None = None):
        now = now or datetime.now(timezone.utc)
        async with self.sessions() as session:
            users = list(
                (
                    await session.scalars(
                        select(UserSettings).where(
                            UserSettings.enabled.is_(True), UserSettings.registered.is_(True)
                        )
                    )
                ).all()
            )
        for prefs in users:
            local = now.astimezone(ZoneInfo(prefs.timezone))
            # Catch up on a restart later the same day, never deliver previous-day summaries.
            if local.time().replace(tzinfo=None) < prefs.notify_time:
                continue
            async with self.sessions() as session:
                message, _ = await summary(session, prefs.user_id, local.date() + timedelta(days=1))
                if prefs.urgent_enabled:
                    done = await completed_ids(session, prefs.user_id)
                    urgent = [
                        h
                        for h in await visible_homework(session, prefs.user_id)
                        if h.due
                        and local.date() <= h.due <= local.date() + timedelta(days=1)
                        and h.id not in done
                    ]
                    if urgent:
                        message = limit_html(message, 3700)
                        message += f"\n\n🚨 Горит дедлайн! Невыполненных срочных заданий: {len(urgent)}.\n💀 Дедлайныч предупреждал!"
            if not await self.claim(prefs.user_id, local.date(), "daily"):
                continue
            status = "sent"
            try:
                await self.bot.send_message(prefs.user_id, message)
            except TelegramForbiddenError:
                status = "blocked"
                async with self.sessions() as session:
                    row = await session.get(UserSettings, prefs.user_id)
                    row.enabled = False
                    await session.commit()
            except (TelegramRetryAfter, TelegramAPIError):
                status = "uncertain"
                log.warning("Доставка сводки не подтверждена")
            async with self.sessions() as session:
                row = await session.get(NotificationHistory, (prefs.user_id, local.date(), "daily"))
                row.status = status
                await session.commit()


async def scheduler_lock(engine, wait_seconds: float = 0):
    """Keep the new Render worker idle until the previous worker releases leadership."""
    connection = await engine.connect()
    connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
    if engine.dialect.name != "postgresql":
        return connection
    expires = asyncio.get_running_loop().time() + wait_seconds
    announced = False
    try:
        while not await connection.scalar(text("SELECT pg_try_advisory_lock(:id)"), {"id": LOCK_ID}):
            remaining = expires - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise RuntimeError("Другой экземпляр Дедлайныча уже работает")
            if not announced:
                log.info("Ожидание завершения предыдущего экземпляра; Telegram polling ещё не запущен")
                announced = True
            await asyncio.sleep(min(1, remaining))
    except BaseException:
        await connection.close()
        raise
    return connection
