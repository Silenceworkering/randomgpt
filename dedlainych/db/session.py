from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dedlainych.config import settings


def make_database(url: str | None = None):
    engine = create_async_engine(url or settings().database_url.get_secret_value(), pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)
