"""Bound Telegram HTML without cutting an entity or leaving tags unclosed."""

from html.parser import HTMLParser


class _Limiter(HTMLParser):
    def __init__(self, limit: int):
        super().__init__(convert_charrefs=False)
        self.remaining = limit - 100
        self.parts: list[str] = []
        self.stack: list[str] = []
        self.stopped = False

    def append(self, value: str):
        if self.stopped:
            return
        if len(value) > self.remaining:
            self.stopped = True
            return
        self.parts.append(value)
        self.remaining -= len(value)

    def handle_starttag(self, tag, attrs):
        self.append(self.get_starttag_text())
        if not self.stopped:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stopped:
            self.append(f"</{tag}>")
            if self.stack and self.stack[-1] == tag:
                self.stack.pop()

    def handle_data(self, data):
        if not self.stopped and len(data) > self.remaining:
            self.parts.append(data[: self.remaining])
            self.remaining = 0
            self.stopped = True
        else:
            self.append(data)

    def handle_entityref(self, name):
        self.append(f"&{name};")

    def handle_charref(self, name):
        self.append(f"&#{name};")


def limit_html(value: str, limit: int = 4000) -> str:
    parser = _Limiter(limit)
    parser.feed(value)
    result = "".join(parser.parts) + "".join(f"</{tag}>" for tag in reversed(parser.stack))
    return result + ("\n… Подробнее — в архиве 📂" if parser.stopped else "")
