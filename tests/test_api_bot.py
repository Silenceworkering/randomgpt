from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.bot import parse_build, format_build, register_webhook
from app.engine import recommend
from app.schemas import RecommendRequest


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    "path", ["/", "/configurator", "/catalog", "/compare", "/smart", "/saved", "/about"]
)
def test_pages(client, path):
    response = client.get(path)
    assert response.status_code == 200 and "VOLTRIX" in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "script-src 'self'" in response.headers["content-security-policy"]


def test_catalog_and_prices(client):
    data = client.get("/api/catalog").json()
    assert len(data["categories"]) == 8
    assert all(i["price_kind"] == "retailer" for i in data["items"])
    assert all(len(i["stores"]) == 3 for i in data["items"])


def test_http_recommendation_and_check(client):
    response = client.post("/api/recommend", json={"budget": 80000})
    assert response.status_code == 200
    result = response.json()
    checked = client.post(
        "/api/build/check",
        json={"components": {k: v["id"] for k, v in result["components"].items()}},
    )
    assert checked.json()["compatibility"]["complete"]
    assert checked.json()["total_rub"] == result["total_rub"]
    assert client.post("/api/recommend", json={"budget": 15000}).status_code == 422
    assert client.post("/api/recommend", json={"budget": -1}).status_code == 422
    assert (
        client.post(
            "/api/build/check", json={"components": {"cpu": "rtx4060"}}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/recommend",
            content="not-json",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )


def test_compare_api(client):
    result = client.post("/api/compare", json={"ids": ["r5600", "r7600"]})
    assert result.status_code == 200
    assert next(r for r in result.json()["rows"] if r["key"] == "socket")["values"] == [
        "AM4",
        "AM5",
    ]
    assert (
        client.post("/api/compare", json={"ids": ["r5600", "rx6600"]}).status_code
        == 422
    )


def test_payload_limit(client):
    assert client.post("/api/build/check", content="x" * 65537).status_code == 413

    def chunks():
        yield b"x" * 35000
        yield b"x" * 35000

    assert client.post("/api/build/check", content=chunks()).status_code == 413


def test_disabled_webhook(client):
    assert client.post("/telegram/webhook", json={"update_id": 1}).status_code == 503
    assert client.get("/health").json()["telegram_configured"] is False


def setup_mock_bot():
    app.state.bot = AsyncMock()
    app.state.dispatcher = AsyncMock()
    app.state.webhook_secret = "test-secret"


def test_webhook_auth_validation_dedup(client):
    setup_mock_bot()
    assert client.post("/telegram/webhook", json={"update_id": 1}).status_code == 403
    headers = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}
    assert client.post("/telegram/webhook", json={}, headers=headers).status_code == 400
    assert (
        client.post("/telegram/webhook", content="{", headers=headers).status_code
        == 400
    )
    for _ in range(2):
        assert (
            client.post(
                "/telegram/webhook", json={"update_id": 1}, headers=headers
            ).status_code
            == 200
        )
    assert app.state.dispatcher.feed_update.await_count == 1


def test_webhook_retry_after_failed_handler(client):
    setup_mock_bot()
    app.state.dispatcher.feed_update.side_effect = RuntimeError("test failure")
    headers = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}
    assert (
        client.post(
            "/telegram/webhook", json={"update_id": 2}, headers=headers
        ).status_code
        == 503
    )
    assert 2 not in app.state.processed_updates
    app.state.dispatcher.feed_update.side_effect = None
    assert (
        client.post(
            "/telegram/webhook", json={"update_id": 2}, headers=headers
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "command",
    ["/build 80000 gaming AMD NVIDIA", "/build@voltrix_bot 80000 игры AMD NVIDIA"],
)
def test_bot_uses_same_algorithm(command):
    request = parse_build(command)
    assert request == RecommendRequest(
        budget=80000, purpose="gaming", cpu_brand="AMD", gpu_brand="NVIDIA"
    )
    result = recommend(request)
    text = format_build(result, "https://example.onrender.com")
    assert "Цены на момент проверки" in text and "/configurator?parts=" in text
    assert all(i["name"] in text for i in result["components"].values())


@pytest.mark.parametrize(
    "command",
    [
        "/build",
        "/build abc",
        "/build -200",
        "/build 100",
        "/build 80000 unknown",
        "/build 80000 gaming AMD Intel",
        "/build 80000 gaming AMD NVIDIA extra",
    ],
)
def test_invalid_bot_commands(command):
    with pytest.raises(ValueError):
        parse_build(command)


def test_webhook_registration():
    import asyncio

    bot = AsyncMock()
    asyncio.run(register_webhook(bot, "https://example.onrender.com", "secret"))
    args = bot.set_webhook.call_args.kwargs
    assert args["secret_token"] == "secret"
    assert args["drop_pending_updates"] is False
    assert args["max_connections"] == 1
    assert args["url"].endswith("/telegram/webhook")


def test_render_url_auto_registration(monkeypatch):
    import app.main as module

    token = "123456:abcdefghijklmnopqrstuvwxyz123456789"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://voltrix-test.onrender.com")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s" * 40)
    bot = AsyncMock()
    factory = AsyncMock()
    # Bot construction is synchronous, its session methods are asynchronous.
    from unittest.mock import Mock

    constructor = Mock(return_value=bot)
    monkeypatch.setattr(module, "Bot", constructor)
    monkeypatch.setattr(module, "register_webhook", factory)
    with TestClient(app) as test_client:
        status = test_client.get("/health").json()
        assert status["telegram_configured"] and status["telegram_registered"]
        factory.assert_awaited_once_with(
            bot, "https://voltrix-test.onrender.com", "s" * 40
        )
    bot.session.close.assert_awaited_once()


@pytest.mark.parametrize(
    "url,secret",
    [
        ("http://insecure.example", "s" * 40),
        ("https://secure.example", "short"),
        ("https://user:password@example.com", "s" * 40),
        ("https://example.com/subpath", "s" * 40),
        ("https://[broken", "s" * 40),
        ("https://example.com:not-a-port", "s" * 40),
    ],
)
def test_bad_bot_config_keeps_site_available(monkeypatch, url, secret):
    monkeypatch.setenv(
        "TELEGRAM_BOT_TOKEN", "123456:abcdefghijklmnopqrstuvwxyz123456789"
    )
    monkeypatch.setenv("PUBLIC_BASE_URL", url)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", secret)
    with TestClient(app) as test_client:
        assert test_client.get("/").status_code == 200
        assert test_client.get("/health").json()["telegram_configured"] is False


def test_real_aiogram_build_handler(monkeypatch):
    import asyncio
    from aiogram import Bot
    from aiogram.types import Update, Message
    from app.bot import create_dispatcher

    req = RecommendRequest(budget=80000, purpose="gaming")
    result = recommend(req)
    search = AsyncMock(return_value=result)
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    bot = Bot(token="123456:abcdefghijklmnopqrstuvwxyz123456789")
    update = Update.model_validate(
        {
            "update_id": 123,
            "message": {
                "message_id": 1,
                "date": 1700000000,
                "chat": {"id": 1, "type": "private"},
                "from": {"id": 1, "is_bot": False, "first_name": "Test"},
                "text": "/build 80000 gaming",
                "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
            },
        },
        context={"bot": bot},
    )

    async def run():
        dispatcher = create_dispatcher(search, "https://example.com")
        await dispatcher.feed_update(bot, update)
        await bot.session.close()

    asyncio.run(run())
    search.assert_awaited_once_with(req)
    assert (
        answer.await_count == 1
        and "Цены на момент проверки" in answer.call_args.args[0]
    )
