"""Synthetic prices belong to tests only, never to the production catalog."""

import json
from pathlib import Path
import pytest
from app.catalog import ITEMS
from app.prices import BOOK, utcnow


@pytest.fixture(autouse=True)
def isolated_prices(monkeypatch):
    monkeypatch.setenv("PRICES_AUTO_REFRESH", "false")
    values = json.loads((Path(__file__).parent / "fixtures/prices.json").read_text())
    records = {}
    sources = []
    for item_id in ITEMS:
        url = "https://www.kns.ru/product/test-fixture-" + item_id + "/"
        snapshot = {
            "price_rub": values.get(item_id, 1_000_000),
            "available": True,
            "checked_at": utcnow().isoformat(),
            "method": "test_fixture",
            "error": None,
        }
        sources.append(
            {
                "item_id": item_id,
                "store": "Тестовый магазин",
                "url": url,
                "region": "Тест",
                "match_tokens": [item_id],
                "snapshot": snapshot,
            }
        )
        records[url] = snapshot
    monkeypatch.setattr(BOOK, "sources", sources)
    monkeypatch.setattr(BOOK, "records", records)
    monkeypatch.setattr(BOOK, "refreshing", False)
    monkeypatch.setattr(BOOK, "last_refresh_at", None)
