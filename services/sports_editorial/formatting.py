from html import escape
from html.parser import HTMLParser


ALLOWED_TAGS = {"strong", "b", "em", "i", "br"}


class _SafeRichTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ALLOWED_TAGS:
            normalised = {"b": "strong", "i": "em"}.get(tag, tag)
            self.parts.append(f"<{normalised}>")

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.parts.append("<br>")

    def handle_endtag(self, tag):
        if tag in ALLOWED_TAGS and tag != "br":
            normalised = {"b": "strong", "i": "em"}.get(tag, tag)
            self.parts.append(f"</{normalised}>")

    def handle_data(self, data):
        self.parts.append(escape(data))


class _PlainTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.parts.append("\n")


def sanitise_rich_text(value):
    parser = _SafeRichTextParser()
    parser.feed(str(value or ""))
    parser.close()
    return "".join(parser.parts).strip()


def rich_text_to_plain(value):
    parser = _PlainTextParser()
    parser.feed(str(value or ""))
    parser.close()
    return "".join(parser.parts).strip()
