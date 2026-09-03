from html import escape
from html.parser import HTMLParser
import re
from urllib.parse import urlparse


ALLOWED_TAGS = {"strong", "b", "em", "i", "sup", "br"}


def _safe_manual_href(attrs):
    values = dict(attrs)
    parsed = urlparse(str(values.get("href") or ""))
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return escape(parsed.geturl(), quote=True)


class _SafeRichTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.anchor_stack = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = _safe_manual_href(attrs)
            self.anchor_stack.append(bool(href))
            if href:
                self.parts.append(f'<a href="{href}" target="_blank" rel="noopener" data-manual-link="true">')
            return
        if tag in ALLOWED_TAGS:
            normalised = {"b": "strong", "i": "em"}.get(tag, tag)
            self.parts.append(f"<{normalised}>")

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.parts.append("<br>")

    def handle_endtag(self, tag):
        if tag == "a":
            if self.anchor_stack and self.anchor_stack.pop():
                self.parts.append("</a>")
            return
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


def _entity_href(entity):
    parsed = urlparse(str(entity.get("canonical_url") or ""))
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return escape(str(entity["canonical_url"]), quote=True)


class _EntityOccurrenceRenderer(HTMLParser):
    """Decorate exact text occurrences without ever matching inside markup."""

    def __init__(self, replacements, published):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.replacements = sorted(replacements, key=lambda item: len(item["mention"]), reverse=True)
        self.published = published
        self.linked_entity_ids = set()
        self.manual_anchor_stack = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = _safe_manual_href(attrs)
            self.manual_anchor_stack.append(bool(href))
            if href:
                self.parts.append(f'<a href="{href}" target="_blank" rel="noopener" data-manual-link="true">')
            return
        if tag in ALLOWED_TAGS:
            normalised = {"b": "strong", "i": "em"}.get(tag, tag)
            self.parts.append(f"<{normalised}>")

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.parts.append("<br>")

    def handle_endtag(self, tag):
        if tag == "a":
            if self.manual_anchor_stack and self.manual_anchor_stack.pop():
                self.parts.append("</a>")
            return
        if tag in ALLOWED_TAGS and tag != "br":
            normalised = {"b": "strong", "i": "em"}.get(tag, tag)
            self.parts.append(f"</{normalised}>")

    def handle_data(self, data):
        if not data or not self.replacements or any(self.manual_anchor_stack):
            self.parts.append(escape(data))
            return
        available = [item for item in self.replacements if item["id"] not in self.linked_entity_ids]
        if not available:
            self.parts.append(escape(data))
            return
        pattern = re.compile("|".join(re.escape(item["mention"]) for item in available))
        by_mention = {item["mention"]: item for item in self.replacements}
        cursor = 0
        for match in pattern.finditer(data):
            self.parts.append(escape(data[cursor:match.start()]))
            item = by_mention[match.group(0)]
            mention = escape(match.group(0))
            if item["id"] in self.linked_entity_ids:
                self.parts.append(mention)
                cursor = match.end()
                continue
            self.linked_entity_ids.add(item["id"])
            if self.published:
                self.parts.append(
                    f'<a class="sew-entity-text-link" href="{item["href"]}" target="_blank" '
                    f'rel="noopener" data-entity-ref="{item["id"]}">{mention}</a>'
                )
            else:
                self.parts.append(
                    f'<span class="sew-entity-text-tag" '
                    f'data-entity-ref="{item["id"]}">{mention}</span>'
                )
            cursor = match.end()
        self.parts.append(escape(data[cursor:]))


def _render_entity_occurrences(value, block, entities_by_id, published):
    replacements = []
    for entity_id in block.get("entity_ids", []):
        entity = entities_by_id.get(entity_id) or {}
        mention = str((block.get("entity_mentions") or {}).get(entity_id) or "").strip()
        href = _entity_href(entity)
        if not mention or (published and not href):
            continue
        replacements.append({
            "id": escape(str(entity_id), quote=True),
            "mention": mention,
            "href": href,
        })
    parser = _EntityOccurrenceRenderer(replacements, published)
    parser.feed(sanitise_rich_text(value))
    parser.close()
    return "".join(parser.parts).strip()


def render_entity_links(value, block, entities_by_id):
    """Link the first exact confirmed occurrence while preserving safe formatting."""
    return _render_entity_occurrences(value, block, entities_by_id, published=True)


def render_entity_tags(value, block, entities_by_id=None):
    entities_by_id = entities_by_id or {entity_id: {} for entity_id in block.get("entity_ids", [])}
    return _render_entity_occurrences(value, block, entities_by_id, published=False)
