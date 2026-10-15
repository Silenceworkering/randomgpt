"""Upgrade a populated legacy schema, not just empty metadata."""

import os
import subprocess
import sys
import uuid

import asyncpg
import pytest
from sqlalchemy.engine import make_url


async def test_populated_postgres_upgrade_preserves_homework_and_completion():
    value = os.getenv("TEST_DATABASE_URL", "")
    if not value.startswith("postgresql"):
        pytest.skip("Миграция проверяется на PostgreSQL в CI")
    address = make_url(value)
    if "test" not in (address.database or "").lower():
        raise RuntimeError("Требуется отдельная тестовая PostgreSQL")
    admin = await asyncpg.connect(address.set(drivername="postgresql").render_as_string(hide_password=False))
    dbname = "dedlainych_upgrade_test_" + uuid.uuid4().hex[:8]
    await admin.execute(f'CREATE DATABASE "{dbname}"')
    url = address.set(database=dbname, drivername="postgresql").render_as_string(hide_password=False)
    env = dict(os.environ, DATABASE_URL=url, PYTHONPATH=".")
    conn = None
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "37ea12000001"],
            env=env,
            check=True,
            capture_output=True,
        )
        conn = await asyncpg.connect(url)
        await conn.execute("""
            INSERT INTO subjects (id,group_code,name,aliases) VALUES (800,'fixture','Матан','[]');
            INSERT INTO homework_sources (id,chat_id,message_id,text,received_at)
              VALUES (800,-100999,1,'Синтетическое условие',now());
            INSERT INTO homework (id,group_code,subject_id,source_id,description,due,subgroup,status,fingerprint,created_at)
              VALUES (800,'fixture',800,800,'Сохранить прежнее условие','2026-10-16',0,'approved',repeat('a',64),now());
            INSERT INTO users (id,group_code,created_at) VALUES (800,'fixture',now());
            INSERT INTO homework_completion (user_id,homework_id,completed_at) VALUES (800,800,now());
        """)
        await conn.close()
        conn = None
        for command in [("upgrade", "head"), ("check",)]:
            subprocess.run(
                [sys.executable, "-m", "alembic", *command], env=env, check=True, capture_output=True
            )
        conn = await asyncpg.connect(url)
        row = await conn.fetchrow("SELECT description,status,operation FROM homework WHERE id=800")
        assert dict(row) == dict(
            description="Сохранить прежнее условие", status="approved", operation="create"
        )
        assert await conn.fetchval("SELECT count(*) FROM homework_completion WHERE user_id=800") == 1
        assert await conn.fetchval("SELECT count(*) FROM homework_sources WHERE id=800") == 1
    finally:
        if conn is not None:
            await conn.close()
        # Only this test's freshly created UUID-named database can be dropped.
        await admin.execute(f'DROP DATABASE "{dbname}" WITH (FORCE)')
        await admin.close()
