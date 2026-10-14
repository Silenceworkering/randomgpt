import asyncio
from datetime import timedelta
import json
import pytest
import httpx
from app.prices import PriceBook, parse_product, utcnow, BOOK
from app.engine import evaluate, recommend, NoBuildError
from app.schemas import BuildRequest, RecommendRequest
from app.catalog import ITEMS

SOURCE = {
    "item_id": "ddr4-32",
    "store": "KNS",
    "region": "Москва",
    "url": "https://www.kns.ru/product/ram-kf432c16bbk2-32/",
    "match_tokens": ["Kingston", "KF432C16BBK2/32"],
    "snapshot": {
        "price_rub": 36220,
        "available": True,
        "checked_at": utcnow().isoformat(),
        "method": "page_snapshot",
    },
}


def page(price="36 220", stock="В наличии на складе", sku="KF432C16BBK2/32"):
    return f"<html><body><h1>Kingston FURY Beast {sku}</h1><div>Цена: <del>65 430 руб.</del> {price} руб. 35 999 руб. Клубная цена {price} руб.</div><div>Наличие: {stock}</div><h2>ОПИСАНИЕ</h2><h3>Другой товар</h3>100 руб. В наличии</body></html>"


def test_regular_price_excludes_club_and_crossed_out():
    assert parse_product(page(), SOURCE) == {"price_rub": 36220, "available": True}


@pytest.mark.parametrize(
    "stock", ["Нет в наличии", "Нет в наличии более 60 дней", "Ожидается", "Под заказ"]
)
def test_unavailable_does_not_use_old_price(stock):
    assert parse_product(page(stock=stock), SOURCE) == {
        "price_rub": None,
        "available": False,
    }


def test_last_price_is_not_an_offer():
    assert (
        parse_product(page().replace("Цена:", "Последняя цена:"), SOURCE)["price_rub"]
        is None
    )


def test_wrong_product_sku_is_rejected():
    with pytest.raises(ValueError):
        parse_product(page(sku="KF432C16BBK2/64"), SOURCE)


def test_no_main_price_never_uses_recommendations():
    html = (
        "<h1>Kingston KF432C16BBK2/32</h1>Нет данных<h2>ОПИСАНИЕ</h2>100 руб. В наличии"
    )
    with pytest.raises(ValueError):
        parse_product(html, SOURCE)


@pytest.mark.parametrize("amount", ["0", "2000001", "NaN"])
def test_invalid_price_rejected(amount):
    with pytest.raises(ValueError):
        parse_product(
            page(price=amount).replace("35 999 руб. Клубная цена", ""), SOURCE
        )


def test_regard_full_spec_link_before_purchase_block():
    source = {**SOURCE, "match_tokens": ["AMD", "Ryzen 5 5600 OEM"]}
    html = "<h1>Процессор AMD Ryzen 5 5600 OEM</h1>Полные характеристики<div>11 610 ₽</div>В наличии<h2>ХАРАКТЕРИСТИКИ</h2>999 ₽"
    assert parse_product(html, source)["price_rub"] == 11610


def test_old_discount_percentage_not_current_price():
    html = "<h1>Kingston KF432C16BBK2/32</h1>Цена: 65430 руб. 10,71% 58420 руб. 58128 руб. Клубная цена 58420 руб. В наличии<h2>ОПИСАНИЕ</h2>"
    assert parse_product(html, SOURCE)["price_rub"] == 58420


def test_book_expiry_and_future_timestamps():
    book = PriceBook([SOURCE])
    now = utcnow()
    assert book.best("ddr4-32")
    assert book.best("ddr4-32", book.snapshot(now + timedelta(hours=25))) is None
    assert book.best("ddr4-32", book.snapshot(now - timedelta(days=1))) is None


def test_best_offer_is_minimum_of_fresh_in_stock_only():
    sources = [
        SOURCE,
        {
            **SOURCE,
            "url": "https://www.regard.ru/product/1/ram",
            "snapshot": {**SOURCE["snapshot"], "price_rub": 7000, "available": False},
        },
        {
            **SOURCE,
            "url": "https://www.regard.ru/product/2/ram",
            "snapshot": {**SOURCE["snapshot"], "price_rub": 35000},
        },
    ]
    assert PriceBook(sources).best("ddr4-32")["price_rub"] == 35000


@pytest.mark.parametrize(
    "url",
    [
        "http://www.kns.ru/product/x/",
        "https://evil.example/product/x/",
        "https://www.kns.ru/search/",
        "https://user:pass@www.kns.ru/product/x/",
    ],
)
def test_source_allowlist(url):
    with pytest.raises(ValueError):
        PriceBook([{**SOURCE, "url": url}])


def test_unknown_price_null_total_never_zero_or_estimate(monkeypatch):
    monkeypatch.setattr(BOOK, "sources", [])
    result = evaluate(BuildRequest(components={"ram": "ddr4-32"}))
    assert result["total_rub"] is None and result["known_total_rub"] == 0
    assert result["unpriced_ids"] == ["ddr4-32"]
    assert result["components"]["ram"]["calculation_rub"] is None
    assert not result["pricing_complete"]
    with pytest.raises(NoBuildError, match="Нет свежих цен"):
        recommend(RecommendRequest(budget=500000))
    manual = evaluate(
        BuildRequest(components={"ram": "ddr4-32"}, price_overrides={"ddr4-32": 31000})
    )
    assert manual["total_rub"] == 31000 and manual["components"]["ram"]["user_price"]


def test_refresh_success_and_failure_without_extending_freshness():
    book = PriceBook([SOURCE])

    async def run():
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200, text=page(), headers={"content-type": "text/html"}
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            await book.refresh(client)
        record = book.records[SOURCE["url"]]
        assert record["method"] == "direct_fetch" and record["price_rub"] == 36220
        checked = record["checked_at"]
        denied = httpx.MockTransport(lambda request: httpx.Response(403))
        async with httpx.AsyncClient(transport=denied) as client:
            await book.refresh(client)
        assert book.records[SOURCE["url"]]["checked_at"] == checked
        assert book.records[SOURCE["url"]]["error"]

    asyncio.run(run())


def test_refresh_out_of_stock_clears_previous_price():
    book = PriceBook([SOURCE])

    async def run():
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text=page(stock="Нет в наличии"),
                headers={"content-type": "text/html"},
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            await book.refresh(client)

    asyncio.run(run())
    assert book.best("ddr4-32") is None
    assert book.records[SOURCE["url"]]["price_rub"] is None


def test_no_production_estimates_or_historical_prices():
    assert all("estimate_rub" not in item for item in ITEMS.values())
    from app.prices import SOURCES

    assert all(
        s["snapshot"]["price_rub"] is None
        for s in SOURCES
        if not s["snapshot"]["available"]
    )
    assert all(s["item_id"] in ITEMS for s in SOURCES)


def test_partial_quote_preserves_known_sum(monkeypatch):
    monkeypatch.setattr(BOOK, "sources", [])
    result = evaluate(
        BuildRequest(
            components={"cpu": "r5600", "ram": "ddr4-32"},
            price_overrides={"r5600": 15000},
        )
    )
    assert result["total_rub"] is None and result["known_total_rub"] == 15000


def test_no_oversized_body_or_redirect_price():
    book = PriceBook([SOURCE])
    original = book.records[SOURCE["url"]]["checked_at"]

    async def run():
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                302, headers={"location": "https://evil.example/"}
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            await book.refresh(client)

    asyncio.run(run())
    assert book.records[SOURCE["url"]]["checked_at"] == original
