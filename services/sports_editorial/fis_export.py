import re

from .formatting import rich_text_to_plain


DISCIPLINE_CODES = {
    "alpine_skiing": "AL", "cross_country": "CC", "snowboard": "SB", "freestyle": "FS",
    "ski_jumping": "JP", "nordic_combined": "NK", "speed_skiing": "SS", "telemark": "TM",
}
LINK_TYPES = {"athlete": "athlete", "country": "nation", "event": "event", "competition": "competition"}
TAG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class FisPayloadValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def _parse_event_ids(values):
    event_ids = []
    for value in values or []:
        try:
            event_id = int(value)
        except (TypeError, ValueError):
            continue
        if event_id > 0 and event_id not in event_ids:
            event_ids.append(event_id)
    return event_ids


def build_fis_payload(submission, entities_by_id, expected_version=None, organisation_uuid=None):
    errors = []
    discipline_code = submission.get("fis_discipline_code") or DISCIPLINE_CODES.get(submission.get("sport"))
    event_ids = _parse_event_ids(submission.get("fis_event_ids"))
    if not submission.get("title"):
        errors.append("FIS requires a sheet title.")
    if not discipline_code:
        errors.append("Map this sport to a FIS discipline code.")
    if not event_ids:
        errors.append("Add at least one FIS calendar event ID.")
    if len(event_ids) > 10:
        errors.append("FIS accepts at most 10 event IDs per sheet.")

    sections = []
    current = {"title": None, "genderCode": submission.get("gender") if submission.get("gender") in ("W", "M") else None, "items": []}
    for block in sorted(submission.get("stats", []), key=lambda item: item.get("sort_order", 0)):
        block_type = block.get("content_type", "stat")
        formatted_text = block.get("edited_text") or block.get("stat_text") or ""
        text = rich_text_to_plain(formatted_text)
        if block_type in ("section", "heading"):
            if current["items"]:
                sections.append(current)
            current = {"title": text or None, "genderCode": submission.get("gender") if submission.get("gender") in ("W", "M") else None, "items": []}
            continue
        if not text:
            errors.append(f"Statistic {block.get('id')} has no publication text.")
            continue
        links = []
        for entity_id in block.get("entity_ids", []):
            entity = entities_by_id.get(entity_id)
            canonical_id = (entity or {}).get("canonical_id")
            link_type = LINK_TYPES.get((entity or {}).get("entity_type"))
            if not entity or not canonical_id or not link_type:
                errors.append(f"Statistic {block.get('id')} has an entity without a FIS-compatible canonical ID.")
                continue
            links.append({"type": link_type, "id": str(canonical_id)})
        tags = [tag.strip() for tag in block.get("tags", []) if tag.strip()]
        invalid_tags = [tag for tag in tags if len(tag) > 40 or not TAG_PATTERN.fullmatch(tag)]
        if invalid_tags:
            errors.append(f"Statistic {block.get('id')} has invalid FIS tags: {', '.join(invalid_tags)}.")
        item = {"clientId": str(block["id"])[:50], "text": text, "links": links}
        if tags:
            item["tags"] = tags[:10]
        current["items"].append(item)
    if current["items"]:
        sections.append(current)
    if not sections:
        errors.append("FIS requires at least one non-empty section.")
    if len(sections) > 20:
        errors.append("FIS accepts at most 20 sections.")
    if sum(len(section["items"]) for section in sections) > 200:
        errors.append("FIS accepts at most 200 items per sheet.")
    if errors:
        raise FisPayloadValidationError(errors)

    payload = {
        "schemaVersion": 1,
        "title": submission["title"][:255],
        "disciplineCode": discipline_code,
        "eventIds": event_ids,
        "sections": sections,
    }
    if submission.get("editor_notes"):
        payload["notes"] = submission["editor_notes"][:2000]
    if expected_version is not None:
        payload["expectedVersion"] = expected_version
    if organisation_uuid:
        payload["organisationUuid"] = organisation_uuid
    return payload
