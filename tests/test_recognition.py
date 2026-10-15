"""Contract tests: no semantic-success claims from a mocked model response."""

import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select, func

from dedlainych.config import Settings
from dedlainych.db.models import AIUsage, ChatContext, ConnectedChat, Source, utcnow
from dedlainych.db.repositories import ingest, purge_context
from dedlainych.services.ai import Analyzer, deadline
from dedlainych.services.ai_budget import reserve_call
from dedlainych.services.group_6104 import configure_week
from dedlainych.services.revisions import approve

SUBJECTS = {
    "Математический анализ": ["матану", "матан"],
    "Иностранный язык": ["англичанка"],
    "История России": ["истории"],
}


@pytest.mark.parametrize(
    "text",
    [
        "Нам к пятнице 24 номер и вопросы на 14 странице",
        "Англичанка сказала второй текст пересказывать",
        "По матану 15–20",
        "Не забудьте таблицу до среды",
        "Короче, вместо 24 делаем 26",
        "Это только для первой подгруппы",
        "Препод перенёс сдачу на понедельник",
    ],
)
def test_requested_examples_are_candidates(text):
    rows = Analyzer.rules(text, SUBJECTS, utcnow().date())
    assert rows
    if not rows[0].subject or rows[0].operation != "create":
        assert rows[0].confidence < 0.8


@pytest.mark.parametrize(
    "text",
    [
        "Что задали по матану?",
        "По матану решить 24?",
        "Кто сделал таблицу по истории?",
        "Я решил по матану №24",
        "Всем привет!",
        "По истории ничего не задали",
        "По матану ДЗ нет",
    ],
)
def test_questions_negations_and_conversation_are_not_tasks(text):
    assert Analyzer.rules(text, SUBJECTS, utcnow().date()) == []


@pytest.mark.parametrize(
    "text", ["По матану возможно решить №24", "По истории решить №100000 ахах", "По истории таблица красивая"]
)
def test_ambiguous_text_never_auto_approved(text):
    assert all(t.confidence < 0.8 for t in Analyzer.rules(text, SUBJECTS, utcnow().date()))


def test_per_task_dates_and_verbal_subgroups():
    today = utcnow().date()
    rows = Analyzer.rules(
        "По матану решить №24 до пятницы, а по истории прочитать главу 3 для второй подгруппы",
        SUBJECTS,
        today,
    )
    assert len(rows) == 2 and rows[0].due is not None
    assert rows[1].due is None and rows[1].subgroup == 2
    assert deadline("сдать 16 октября 2026", today).isoformat() == "2026-10-16"


async def setup_group(session):
    today = utcnow().date()
    await configure_week(session, "6104-ОБ", 1, today - timedelta(days=today.weekday()))


async def send(session, text, mid, **kwargs):
    now = utcnow()
    return await ingest(
        session,
        Analyzer(Settings(_env_file=None)),
        -100123,
        mid,
        text,
        [],
        now.date(),
        received_at=kwargs.pop("received_at", now),
        **kwargs,
    )


async def test_context_keeps_non_homework_temporarily_and_infers_subject(database):
    async with database() as session:
        await setup_group(session)
        assert await send(session, "Сейчас обсуждаем матан", 1) == []
        assert await session.scalar(select(Source.id)) is None
        tasks = await send(session, "Нам к пятнице 24 номер", 2)
        assert tasks[0].subject_id and tasks[0].status == "pending"
        assert await session.scalar(select(func.count()).select_from(ChatContext)) == 2


async def test_context_ttl_count_and_chat_isolation(database):
    async with database() as session:
        await setup_group(session)
        session.add(ConnectedChat(id=-100456, group_code="6104-ОБ", title="Other"))
        await session.flush()
        await send(session, "Сейчас обсуждаем матан", 1, received_at=utcnow() - timedelta(hours=3))
        assert await session.get(ChatContext, (-100123, 1)) is None
        rows = await send(session, "Нам 24 номер", 2)
        assert rows[0].subject_id is None
        await send(session, "Сейчас обсуждаем матан", 3)
        elsewhere = await ingest(
            session, Analyzer(Settings(_env_file=None)), -100456, 4, "Решить №80", [], utcnow().date()
        )
        assert elsewhere[0].subject_id is None
        for mid in range(10, 30):
            await send(session, f"обычный разговор {mid}", mid)
        assert (
            await session.scalar(
                select(func.count()).select_from(ChatContext).where(ChatContext.chat_id == -100123)
            )
            == 12
        )
        for row in (await session.scalars(select(ChatContext))).all():
            row.expires_at = utcnow() - timedelta(seconds=1)
        await session.flush()
        await purge_context(session)
        assert await session.scalar(select(func.count()).select_from(ChatContext)) == 0


async def test_correction_does_not_replace_until_approval_and_is_idempotent(database):
    async with database() as session:
        await setup_group(session)
        original = (await send(session, "По матану решить №24", 1))[0]
        proposal = (await send(session, "Короче, вместо 24 делаем 26", 2, reply_to_message_id=1))[0]
        assert original.status == "approved" and proposal.status == "pending"
        assert proposal.target_id == original.id and "26" in proposal.description
        assert await send(session, "Короче, вместо 24 делаем 26", 2, reply_to_message_id=1) == []
        await approve(session, proposal.id, "6104-ОБ")
        assert original.status == "superseded" and proposal.status == "approved"
        await approve(session, proposal.id, "6104-ОБ")


async def test_due_and_subgroup_changes_preserve_description(database):
    async with database() as session:
        await setup_group(session)
        original = (await send(session, "По матану решить №24", 1))[0]
        proposal = (await send(session, "Препод перенёс сдачу на понедельник", 2, reply_to_message_id=1))[0]
        assert proposal.description == original.description and proposal.due is not None
        await approve(session, proposal.id, "6104-ОБ")
        change = (await send(session, "Это только для первой подгруппы", 3, reply_to_message_id=2))[0]
        assert change.target_id == proposal.id and change.subgroup == 1
        assert change.description == original.description and change.due == proposal.due
        assert proposal.status == "approved"


async def test_unresolved_and_conflicting_changes_require_review(database):
    async with database() as session:
        await setup_group(session)
        a = (await send(session, "По матану решить №24", 1))[0]
        b = (await send(session, "История России: прочитать главу 3", 2))[0]
        unknown = (await send(session, "Препод перенёс сдачу на понедельник", 3))[0]
        assert unknown.target_id is None and a.status == b.status == "approved"
        with pytest.raises(ValueError, match="исходное"):
            await approve(session, unknown.id, "6104-ОБ")
        proposal = (await send(session, "Отменили задание", 4, reply_to_message_id=1))[0]
        a.description = "Администратор уточнил условие"
        await session.flush()
        with pytest.raises(ValueError, match="изменилось"):
            await approve(session, proposal.id, "6104-ОБ")
        assert a.status == "approved"


async def test_cancellation_does_not_delete_materials(database):
    async with database() as session:
        await setup_group(session)
        original = (await send(session, "По матану решить №24", 1))[0]
        proposal = (await send(session, "Отменили задание", 2, reply_to_message_id=1))[0]
        assert original.status == "approved"
        await approve(session, proposal.id, "6104-ОБ")
        assert original.status == proposal.status == "rejected"
        assert await session.get(Source, original.source_id)


async def test_edit_and_stale_delivery_keep_original(database):
    async with database() as session:
        await setup_group(session)
        now = utcnow()
        old = (await send(session, "По матану решить №24", 1, version_at=now))[0]
        rows = await send(session, "А что вообще задали?", 1, version_at=now + timedelta(seconds=2))
        assert old.status == "approved" and rows[0].status == "pending"
        assert await send(session, "По матану решить №25", 1, version_at=now - timedelta(seconds=1)) == []
        source = await session.get(Source, old.source_id)
        assert source.text == "А что вообще задали?"


async def test_forwarded_task_pending(database):
    async with database() as session:
        await setup_group(session)
        rows = await send(session, "По матану решить №24", 1, forwarded=True)
        assert rows[0].status == "pending"


async def test_model_runs_without_homework_keyword_and_does_not_invent_date():
    config = Settings(
        _env_file=None, ai_provider="groq", ai_external_enabled=True, ai_api_key="synthetic-test-key"
    )
    analyzer = Analyzer(config)
    body = json.dumps(
        {
            "kind": "assignment",
            "tasks": [
                {
                    "subject": "Иностранный язык",
                    "description": "Пересказать второй текст",
                    "due": "2030-01-01",
                    "subgroup": 2,
                    "confidence": 0.99,
                    "evidence": "Второй текст своими словами, сказала она",
                }
            ],
        }
    )
    with patch.object(analyzer, "_infer", new=AsyncMock(return_value=body)) as infer:
        tasks = await analyzer.extract(
            "Второй текст своими словами, сказала она",
            SUBJECTS,
            utcnow().date(),
            reserve=AsyncMock(return_value=True),
        )
    infer.assert_awaited_once()
    assert tasks[0].due is None and tasks[0].subgroup == 0 and tasks[0].confidence < 0.8


@pytest.mark.parametrize("kind", ["question", "joke", "speculation", "conversation"])
async def test_semantic_classification_can_reject_ambiguous_candidate(kind):
    analyzer = Analyzer(Settings(_env_file=None, ai_provider="ollama"))
    with patch.object(analyzer, "_infer", new=AsyncMock(return_value=json.dumps(dict(kind=kind, tasks=[])))):
        assert await analyzer.extract("Может таблицу сделать", SUBJECTS, utcnow().date()) == []


async def test_external_disabled_and_quota_exhausted_never_call_api():
    for enabled in [False, True]:
        analyzer = Analyzer(
            Settings(
                _env_file=None,
                ai_provider="groq",
                ai_external_enabled=enabled,
                ai_api_key="synthetic-test-key",
            )
        )
        with patch.object(analyzer, "_infer", new=AsyncMock()) as infer:
            await analyzer.extract(
                "Вместо 24 делаем 26", SUBJECTS, utcnow().date(), reserve=AsyncMock(return_value=False)
            )
            infer.assert_not_awaited()


@pytest.mark.parametrize("error", [httpx.ConnectError("unavailable"), ValueError("invalid JSON")])
async def test_inference_errors_fall_back_without_leaking_secrets(error, caplog):
    analyzer = Analyzer(Settings(_env_file=None, ai_provider="ollama"))
    with patch.object(analyzer, "_infer", new=AsyncMock(side_effect=error)):
        result = await analyzer.extract("Нам к пятнице 24 номер", SUBJECTS, utcnow().date())
    assert result and analyzer.last_provider == "rules" and result[0].subject is None
    assert "Нам к пятнице" not in caplog.text


async def test_invalid_evidence_and_schema_fail_closed():
    analyzer = Analyzer(Settings(_env_file=None, ai_provider="ollama"))
    for payload in [
        dict(
            tasks=[dict(subject="История России", description="Прочитать", evidence="из другого сообщения")]
        ),
        dict(tasks=[dict(description="Прочитать", operation="delete_database")]),
    ]:
        with patch.object(analyzer, "_infer", new=AsyncMock(return_value=json.dumps(payload))):
            result = await analyzer.extract("Второй текст своими словами", SUBJECTS, utcnow().date())
        assert result == []


async def test_budget_survives_rollback_and_restart(database):
    engine = database.kw["bind"]
    assert await reserve_call(engine, 2)
    async with database() as session:
        await session.rollback()
    assert await reserve_call(engine, 2)
    assert not await reserve_call(engine, 2)
    assert not await reserve_call(engine, 0)
    async with database() as session:
        assert await session.scalar(select(AIUsage.calls)) == 2


async def test_concurrent_budget_reservations(database):
    engine = database.kw["bind"]
    results = await asyncio.gather(*(reserve_call(engine, 3) for _ in range(8)))
    assert sum(results) == 3


async def test_groq_http_contract_uses_fixed_endpoint_and_bounded_output():
    analyzer = Analyzer(
        Settings(
            _env_file=None, ai_provider="groq", ai_external_enabled=True, ai_api_key="synthetic-key-for-tests"
        )
    )
    response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": '{"kind":"conversation","tasks":[]}'}}]},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=response)) as http:
        assert (
            await analyzer.extract(
                "Они опять поменяли мнение", SUBJECTS, utcnow().date(), reserve=AsyncMock(return_value=True)
            )
            == []
        )
    assert http.call_args.args[0] == "https://api.groq.com/openai/v1/chat/completions"
    assert http.call_args.kwargs["json"]["max_completion_tokens"] == 1536
    assert http.call_args.kwargs["headers"]["Authorization"].startswith("Bearer ")


async def test_replay_does_not_reserve_another_inference_call(database):
    config = Settings(
        _env_file=None, ai_provider="groq", ai_external_enabled=True, ai_api_key="synthetic-test-key"
    )
    analyzer = Analyzer(config)
    evidence = "Нам к пятнице 24 номер"
    payload = json.dumps(dict(tasks=[dict(description=evidence, evidence=evidence)]))
    async with database() as session:
        with patch.object(analyzer, "_infer", new=AsyncMock(return_value=payload)) as infer:
            assert await ingest(session, analyzer, -100123, 1, evidence, [], utcnow().date())
            assert await ingest(session, analyzer, -100123, 1, evidence, [], utcnow().date()) == []
            assert infer.await_count == 1
        assert await session.scalar(select(AIUsage.calls)) == 1


async def test_context_persists_across_sessions(database):
    async with database() as session:
        await setup_group(session)
        await send(session, "Обсуждаем матан", 1)
        await session.commit()
    async with database() as session:
        result = await send(session, "Нам 24 номер", 2)
        assert result[0].subject_id and result[0].status == "pending"


def test_exercise_number_is_not_a_date_and_alias_collision_is_unknown():
    assert deadline("Решить №5.10", utcnow().date()) is None
    tasks = Analyzer.rules(
        "По матеше решить №5", {"Алгебра": ["матеше"], "Матанализ": ["матеше"]}, utcnow().date()
    )
    assert tasks[0].subject is None and tasks[0].confidence < 0.8


async def test_legacy_processed_source_is_not_reanalysed(database):
    async with database() as session:
        source = Source(chat_id=-100123, message_id=1, text="Решить №5")
        session.add(source)
        await session.flush()
        assert await send(session, "Решить №5", 1) == []
        assert source.content_hash


async def test_cross_chat_target_binding_is_forbidden(database):
    from dedlainych.services.revisions import bind_target

    async with database() as session:
        await setup_group(session)
        target = (await send(session, "По матану решить №24", 1))[0]
        session.add(ConnectedChat(id=-100456, group_code="6104-ОБ", title="Other"))
        await session.flush()
        proposal = (
            await ingest(
                session,
                Analyzer(Settings(_env_file=None)),
                -100456,
                2,
                "Вместо 24 делаем 26",
                [],
                utcnow().date(),
            )
        )[0]
        with pytest.raises(ValueError, match="чату"):
            await bind_target(session, proposal, target)
        assert target.status == "approved"


async def test_revision_carries_original_attachment(database):
    from dedlainych.db.models import Attachment

    async with database() as session:
        await setup_group(session)
        old = (await send(session, "По матану решить №24", 1))[0]
        session.add(
            Attachment(source_id=old.source_id, file_id="synthetic-material", kind="photo", name="photo.jpg")
        )
        await session.flush()
        proposal = (await send(session, "Вместо 24 делаем 26", 2, reply_to_message_id=1))[0]
        assert (
            await session.scalar(select(Attachment.file_id).where(Attachment.source_id == proposal.source_id))
            == "synthetic-material"
        )
        assert (
            await session.scalar(select(Attachment.file_id).where(Attachment.source_id == old.source_id))
            == "synthetic-material"
        )


def test_negation_does_not_hide_other_subject_assignment():
    tasks = Analyzer.rules("По истории ДЗ нет, а по матану решить №5", SUBJECTS, utcnow().date())
    assert len(tasks) == 1 and tasks[0].subject == "Математический анализ"


async def test_model_multiple_tasks_keep_separate_evidence_dates():
    analyzer = Analyzer(Settings(_env_file=None, ai_provider="ollama"))
    text = "Нам к пятнице 24 номер. А ещё второй текст пересказать."
    payload = dict(
        tasks=[
            dict(subject="Математический анализ", description="Номер 24", evidence="Нам к пятнице 24 номер"),
            dict(
                subject="Иностранный язык",
                description="Пересказать второй текст",
                due="2030-01-01",
                evidence="второй текст пересказать",
            ),
        ]
    )
    with patch.object(analyzer, "_infer", new=AsyncMock(return_value=json.dumps(payload))):
        rows = await analyzer.extract(text, SUBJECTS, utcnow().date())
    assert len(rows) == 2 and rows[0].due is not None and rows[1].due is None


async def test_semantic_checker_can_reject_apparent_explicit_instruction():
    analyzer = Analyzer(Settings(_env_file=None, ai_provider="ollama"))
    with patch.object(analyzer, "_infer", new=AsyncMock(return_value='{"kind":"joke","tasks":[]}')) as infer:
        assert await analyzer.extract("По матану решить №24", SUBJECTS, utcnow().date()) == []
        infer.assert_awaited_once()
