import asyncio
from alembic import context
from dedlainych.db.models import Base
from dedlainych.db.session import make_database


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine, _ = make_database()
    async with engine.connect() as connection:
        await connection.run_sync(migrate)
    await engine.dispose()


if context.is_offline_mode():
    from dedlainych.config import settings

    context.configure(
        url=settings().database_url.get_secret_value(), target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
