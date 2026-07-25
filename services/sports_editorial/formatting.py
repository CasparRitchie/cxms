from html import escape
from html.parser import HTMLParser
import re
from urllib.parse import urlparse


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


def render_entity_links(value, block, entities_by_id):
    """Render stored mention text safely; entity identity remains in link rows."""
    rendered = sanitise_rich_text(value)
    for entity_id in block.get("entity_ids", []):
        entity = entities_by_id.get(entity_id) or {}
        mention = str((block.get("entity_mentions") or {}).get(entity_id) or "").strip()
        if not mention:
            continue
        escaped_mention = escape(mention)
        parsed = urlparse(str(entity.get("canonical_url") or ""))
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        anchor = (
            f'<a class="sew-entity-text-link" href="{escape(entity["canonical_url"], quote=True)}" '
            f'target="_blank" rel="noopener" data-entity-ref="{escape(str(entity_id), quote=True)}">'
            f"{escaped_mention}</a>"
        )
        rendered = re.sub(re.escape(escaped_mention), lambda _match: anchor, rendered, count=1)
    return rendered


def render_entity_tags(value, block):
    rendered = sanitise_rich_text(value)
    for entity_id in block.get("entity_ids", []):
        mention = str((block.get("entity_mentions") or {}).get(entity_id) or "").strip()
        if not mention:
            continue
        escaped_mention = escape(mention)
        tag = (
            f'<span class="sew-entity-text-tag" tabindex="0" role="link" '
            f'data-entity-ref="{escape(str(entity_id), quote=True)}">{escaped_mention}</span>'
        )
        rendered = re.sub(re.escape(escaped_mention), lambda _match: tag, rendered, count=1)
    return rendered
