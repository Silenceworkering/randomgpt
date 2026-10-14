"""Retailer prices only. Bounded public-page fetches; no paid API or guessed fallback."""

import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from threading import RLock
from urllib.parse import urlsplit
import httpx

UTC = timezone.utc
MAX_AGE = timedelta(hours=24)
SOURCES = json.loads((Path(__file__).parent / "data/price_sources.json").read_text())[
    "sources"
]
ALLOWED_HOSTS = {"www.kns.ru", "www.regard.ru"}


def utcnow():
    return datetime.now(UTC)


def norm(value):
    return re.sub(r"[^a-zа-яё0-9]", "", str(value).casefold())


class ProductPage(HTMLParser):
    """Extract main product region, excluding scripts, struck-out prices and recommendations."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h1 = ""
        self.in_h1 = False
        self.started = False
        self.skip = 0
        self.text = []
        self.blocks = []
        self.script_type = None
        self.script_text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.script_type = attrs.get("type")
            self.script_text = ""
        if tag in {"script", "style", "del", "s"}:
            self.skip += 1
        if tag == "h1" and not self.started:
            self.in_h1 = True
            self.started = True
        if self.started and not self.skip:
            self.text.append(" ")

    def handle_endtag(self, tag):
        if tag == "script" and self.script_type == "application/ld+json":
            try:
                self.blocks.append(json.loads(self.script_text))
            except (ValueError, TypeError):
                pass
        if tag == "script":
            self.script_type = None
        if tag in {"script", "style", "del", "s"}:
            self.skip = max(0, self.skip - 1)
        if tag == "h1":
            self.in_h1 = False
        if self.started and not self.skip:
            self.text.append(" ")

    def handle_data(self, data):
        if self.script_type == "application/ld+json" and self.skip:
            self.script_text += data
        if not self.skip and self.started:
            self.text.append(data)
            if self.in_h1:
                self.h1 += data


def parse_product(html: str, source: dict) -> dict:
    parser = ProductPage()
    parser.feed(html)
    if not parser.h1 or not all(
        norm(t) in norm(parser.h1) for t in source["match_tokens"]
    ):
        raise ValueError("Product identity could not be verified")
    text = re.sub(r"\s+", " ", " ".join(parser.text)).strip()
    # Restrict to the purchase block before descriptions/specs/recommendations.
    block = re.split(
        r"ОПИСАНИЕ|ХАРАКТЕРИСТИКИ|Технические характеристики|Основные характеристики|Похожие товары|Рекомендуемые товары|Популярные товары",
        text,
        maxsplit=1,
    )[0][:12000]
    if re.search(r"нет в наличии|последняя цена|ожидается|под заказ", block, re.I):
        return {"available": False, "price_rub": None}
    if not re.search(r"в наличии", block, re.I):
        raise ValueError("Availability could not be verified")
    # Never pick a credit payment, club price, crossed-out price or another product.
    amounts = []
    for match in re.finditer(
        r"(?<![\d.,])([\d][\d\s]*(?:[.,]\d{1,2})?)\s*(?:руб\.?|₽)", block
    ):
        tail = block[match.end() : match.end() + 30]
        context = block[max(0, match.start() - 20) : match.start()].lower()
        if re.match(r"\s*[\d.,]+\s*%|\s*клубная|\s*/\s*мес", tail, re.I) or re.search(
            r"клубная|в месяц|кредит|рассроч", context
        ):
            continue
        number = match.group(1).replace(" ", "").replace(",", ".")
        try:
            value = float(number)
        except ValueError:
            continue
        if value.is_integer() and 1 <= value <= 2_000_000:
            amounts.append(int(value))
    if not amounts:
        raise ValueError("Regular RUB price could not be verified")
    # KNS repeats the ordinary purchase price; Regard has one ordinary price.
    counts = Counter(amounts)
    repeated = [v for v in amounts if counts[v] >= 2]
    value = repeated[0] if repeated else amounts[0]
    return {"available": True, "price_rub": value}


class PriceBook:
    def __init__(self, sources=SOURCES):
        self.sources = sources
        self.lock = RLock()
        self.records = {}
        self.refreshing = False
        self.last_refresh_at = None
        for source in sources:
            parsed = urlsplit(source["url"])
            if (
                parsed.scheme != "https"
                or parsed.hostname not in ALLOWED_HOSTS
                or not parsed.path.startswith("/product/")
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Untrusted price source")
            self.records[source["url"]] = {**source["snapshot"], "error": None}

    def snapshot(self, now=None):
        now = now or utcnow()
        result = {}
        with self.lock:
            for source in self.sources:
                record = self.records[source["url"]]
                checked = datetime.fromisoformat(record["checked_at"])
                fresh = timedelta(0) <= now - checked <= MAX_AGE
                public = {
                    **record,
                    "store": source["store"],
                    "url": source["url"],
                    "region": source["region"],
                    "fresh": fresh,
                    "currency": "RUB",
                    "price_kind": (
                        "retailer"
                        if fresh and record["available"]
                        else "unavailable" if fresh else "stale"
                    ),
                }
                result.setdefault(source["item_id"], []).append(public)
        return result

    def best(self, item_id, snapshot=None):
        offers = (snapshot if snapshot is not None else self.snapshot()).get(
            item_id, []
        )
        eligible = [
            o
            for o in offers
            if o["fresh"]
            and o["available"]
            and isinstance(o["price_rub"], int)
            and not isinstance(o["price_rub"], bool)
            and o["price_rub"] > 0
        ]
        return min(eligible, key=lambda o: o["price_rub"]) if eligible else None

    async def refresh(self, client=None):
        if self.refreshing:
            return
        self.refreshing = True
        own = client is None
        if own:
            client = httpx.AsyncClient(
                timeout=15,
                follow_redirects=False,
                headers={"User-Agent": "VOLTRIX/1.1 (public product price checker)"},
            )
        semaphore = asyncio.Semaphore(2)

        async def fetch(source):
            async with semaphore:
                try:
                    async with client.stream("GET", source["url"]) as response:
                        response.raise_for_status()
                        if "text/html" not in response.headers.get("content-type", ""):
                            raise ValueError("Expected HTML")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 3_000_000:
                                raise ValueError("Page too large")
                        parsed = parse_product(
                            body.decode(response.encoding or "utf-8", errors="replace"),
                            source,
                        )
                    with self.lock:
                        self.records[source["url"]] = {
                            **parsed,
                            "checked_at": utcnow().isoformat(),
                            "method": "direct_fetch",
                            "error": None,
                        }
                except (httpx.HTTPError, ValueError, UnicodeError):
                    with self.lock:
                        # Keep original timestamp, never extend freshness on failure.
                        self.records[source["url"]][
                            "error"
                        ] = "Источник временно недоступен или формат страницы изменился."

        try:
            await asyncio.gather(*(fetch(s) for s in self.sources))
            self.last_refresh_at = utcnow().isoformat()
        finally:
            self.refreshing = False
            if own:
                await client.aclose()

    async def run(self):
        while True:
            await self.refresh()
            await asyncio.sleep(3600)


BOOK = PriceBook()
