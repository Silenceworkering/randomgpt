"""Read-only models and current in-memory retailer offers; no runtime database."""

import json
from pathlib import Path
from urllib.parse import quote
from .prices import BOOK

DATA = json.loads((Path(__file__).parent / "data/catalog.json").read_text())
CATEGORIES = {
    "cpu": "Процессоры",
    "gpu": "Видеокарты",
    "motherboard": "Материнские платы",
    "ram": "Оперативная память",
    "ssd": "SSD",
    "psu": "Блоки питания",
    "case": "Корпуса",
    "cooler": "Охлаждение",
}
ITEMS = {item["id"]: item for item in DATA["items"]}
GROUPS = {
    category: [i for i in ITEMS.values() if i["category"] == category]
    for category in CATEGORIES
}


def public_item(item: dict, snapshot=None) -> dict:
    offers = (snapshot if snapshot is not None else BOOK.snapshot()).get(item["id"], [])
    best = BOOK.best(item["id"], snapshot)
    query = quote(item["name"])
    brand = (
        "Sapphire"
        if item["category"] == "gpu" and item["brand"] == "AMD"
        else item["brand"]
    )
    if item["category"] == "gpu" and item["brand"] == "NVIDIA":
        brand = "MSI"
    return {
        **item,
        "price_kind": "retailer" if best else "unknown",
        "price_rub": best["price_rub"] if best else None,
        "best_offer": best,
        "offers": offers,
        "manufacturer_url": DATA["metadata"]["manufacturer_links"].get(brand),
        "stores": [
            {"name": "DNS", "url": "https://www.dns-shop.ru/search/?q=" + query},
            {
                "name": "Ситилинк",
                "url": "https://www.citilink.ru/search/?text=" + query,
            },
            {
                "name": "Яндекс Маркет",
                "url": "https://market.yandex.ru/search?text=" + query,
            },
        ],
    }
