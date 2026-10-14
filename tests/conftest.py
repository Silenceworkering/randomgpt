import os

import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dedlainych.db.models import Base, ConnectedChat, Subject
from dedlainych.db.repositories import register


@pytest_asyncio.fixture
async def database():
    url = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    if not url.startswith("sqlite") and "test" not in (make_url(url).database or "").lower():
        raise RuntimeError("TEST_DATABASE_URL должен указывать на отдельную БД с test в названии")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await register(session, 101, "6104-ОБ")
        await register(session, 102, "6104-ОБ")
        await register(session, 103, "other")
        session.add_all(
            [
                Subject(group_code="6104-ОБ", name="Математика", aliases=["матеша", "матеше"]),
                Subject(group_code="6104-ОБ", name="История", aliases=["истории"]),
                ConnectedChat(id=-100123, group_code="6104-ОБ", title="Учёба"),
            ]
        )
        await session.commit()
    yield sessions
    await engine.dispose()
