"""Read-only catalog shipped with the app: no runtime database or price scraping."""

import json
from pathlib import Path
from urllib.parse import quote

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


def public_item(item: dict) -> dict:
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
        "price_kind": "estimate",
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
