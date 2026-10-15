"""Commit a quota reservation BEFORE HTTP, independently of the message transaction."""

from datetime import timezone, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from dedlainych.db.models import AIUsage


async def reserve_call(engine, limit: int) -> bool:
    if limit <= 0:
        return False
    insert = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    day = datetime.now(timezone.utc).date()
    statement = insert(AIUsage).values(day=day, calls=1)
    statement = statement.on_conflict_do_update(
        index_elements=[AIUsage.day], set_={"calls": AIUsage.calls + 1}, where=AIUsage.calls < limit
    ).returning(AIUsage.calls)
    async with engine.begin() as conn:
        return (await conn.execute(statement)).scalar_one_or_none() is not None
