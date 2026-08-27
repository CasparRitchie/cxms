import re

from .formatting import rich_text_to_plain


DISCIPLINE_CODES = {"alpine_skiing": "AL"}
LINK_TYPES = {"athlete": "athlete", "country": "nation", "event": "event", "competition": "competition"}
TAG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,50}$")


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


def _fis_link(entity):
    canonical_id = (entity or {}).get("canonical_id")
    link_type = LINK_TYPES.get((entity or {}).get("entity_type"))
    if not entity or not canonical_id or not link_type:
        return None
    return {"type": link_type, "id": str(canonical_id)}


def _marked_text(text, block, entities_by_id, errors):
    mentions = block.get("entity_mentions") or {}
    replacements = []
    used_text = {}
    for entity_id, display_text in mentions.items():
        display_text = str(display_text or "").strip()
        if not display_text:
            continue
        entity = entities_by_id.get(entity_id)
        link = _fis_link(entity)
        if not link:
            continue
        if len(display_text) > 100 or any(character in display_text for character in "{}|"):
            errors.append(f"Statistic {block.get('id')} has invalid words-to-link text for {entity.get('name', entity_id)}.")
            continue
        if display_text not in text:
            errors.append(f"Statistic {block.get('id')} cannot link “{display_text}” because those exact words are not in the publication wording.")
            continue
        if display_text in used_text and used_text[display_text] != (link["type"], link["id"]):
            errors.append(f"Statistic {block.get('id')} assigns “{display_text}” to more than one FIS entity.")
            continue
        used_text[display_text] = (link["type"], link["id"])
        replacements.append((display_text, f"{{{{{link['type']}:{link['id']}|{display_text}}}}}"))
    markers = {}
    for index, (display_text, marker) in enumerate(sorted(replacements, key=lambda item: len(item[0]), reverse=True)):
        placeholder = f"\x00FIS{index}\x00"
        text = text.replace(display_text, placeholder, 1)
        markers[placeholder] = marker
    for placeholder, marker in markers.items():
        text = text.replace(placeholder, marker)
    return text


def _validate_link(link, block_id, errors):
    link_type, link_id = link["type"], link["id"]
    if not LINK_ID_PATTERN.fullmatch(link_id):
        errors.append(f"Statistic {block_id} has an invalid {link_type} identifier: {link_id}.")
    elif link_type == "nation" and not re.fullmatch(r"[A-Z]{3}", link_id):
        errors.append(f"Statistic {block_id} nation IDs must be three uppercase FIS letters.")
    elif link_type == "athlete" and not re.fullmatch(r"-?\d+", link_id):
        errors.append(f"Statistic {block_id} athlete IDs must be numeric FIS identifiers, including the signed historic format.")
    elif link_type in ("event", "competition") and not link_id.isdigit():
        errors.append(f"Statistic {block_id} {link_type} IDs must be numeric FIS identifiers.")


def build_fis_payload(submission, entities_by_id, expected_version=None, organisation_uuid=None, calendar_events=None):
    errors = []
    external_id = submission.get("fis_external_id")
    if external_id and not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,99}", external_id):
        errors.append("The FIS external ID must be a stable lowercase slug of 3–100 characters.")
    discipline_code = submission.get("fis_discipline_code") or DISCIPLINE_CODES.get(submission.get("sport"))
    event_ids = _parse_event_ids(submission.get("fis_event_ids"))
    if not submission.get("title"):
        errors.append("FIS requires a sheet title.")
    elif len(submission["title"]) > 255:
        errors.append("The FIS sheet title must be 255 characters or fewer.")
    if not discipline_code:
        errors.append("This pilot currently accepts Alpine Skiing (AL/ALP) only.")
    elif discipline_code != "AL":
        errors.append("This pilot currently accepts Alpine Skiing (AL/ALP) only.")
    if not event_ids:
        errors.append("Add at least one FIS calendar event ID.")
    if len(event_ids) > 10:
        errors.append("FIS accepts at most 10 event IDs per sheet.")
    if calendar_events is not None and event_ids:
        known = {str(event.get("canonical_id")): event for event in calendar_events}
        selected = [known.get(str(event_id)) for event_id in event_ids]
        missing = [str(event_id) for event_id, event in zip(event_ids, selected) if not event]
        if missing:
            errors.append("These FIS calendar event IDs are not in the refreshed catalogue: " + ", ".join(missing) + ".")
        seasons = {str((event.get("metadata") or {}).get("season_code")) for event in selected if event and (event.get("metadata") or {}).get("season_code")}
        if len(seasons) > 1:
            errors.append("All FIS calendar events on a sheet must belong to the same season.")
        wrong_discipline = [event.get("canonical_id") for event in selected if event and (event.get("metadata") or {}).get("discipline_code") not in (None, discipline_code)]
        if wrong_discipline:
            errors.append("All FIS calendar events must use the sheet discipline.")

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
            if len(text) > 255:
                errors.append(f"Section heading {block.get('id')} must be 255 characters or fewer.")
            continue
        if not text:
            errors.append(f"Statistic {block.get('id')} has no publication text.")
            continue
        links = []
        seen_links = set()
        for entity_id in block.get("entity_ids", []):
            entity = entities_by_id.get(entity_id)
            link = _fis_link(entity)
            if not link:
                errors.append(f"Statistic {block.get('id')} has an entity without a FIS-compatible canonical ID.")
                continue
            key = (link["type"], link["id"])
            if key not in seen_links:
                _validate_link(link, block.get("id"), errors)
                links.append(link)
                seen_links.add(key)
        if len(links) > 30:
            errors.append(f"Statistic {block.get('id')} has more than 30 FIS entity links.")
        text = _marked_text(text, block, entities_by_id, errors)
        if len(text) > 5000:
            errors.append(f"Statistic {block.get('id')} exceeds the FIS limit of 5,000 characters after entity linking.")
        tags = [tag.strip() for tag in block.get("tags", []) if tag.strip()]
        invalid_tags = [tag for tag in tags if len(tag) > 40 or not TAG_PATTERN.fullmatch(tag)]
        if invalid_tags:
            errors.append(f"Statistic {block.get('id')} has invalid FIS tags: {', '.join(invalid_tags)}.")
        if len(tags) > 10:
            errors.append(f"Statistic {block.get('id')} has more than 10 FIS tags.")
        client_id = str(block["id"])
        if len(client_id) > 50:
            errors.append(f"Statistic {block.get('id')} has a client ID longer than 50 characters.")
        item = {"clientId": client_id, "text": text, "links": links}
        if tags:
            item["tags"] = tags
        current["items"].append(item)
    if current["items"]:
        sections.append(current)
    if not sections:
        errors.append("FIS requires at least one non-empty section.")
    if len(sections) > 20:
        errors.append("FIS accepts at most 20 sections.")
    if sum(len(section["items"]) for section in sections) > 200:
        errors.append("FIS accepts at most 200 items per sheet.")
    if expected_version is not None and (not isinstance(expected_version, int) or expected_version < 1):
        errors.append("The expected FIS version must be a positive integer.")
    if organisation_uuid and not re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}", organisation_uuid):
        errors.append("The FIS organisation UUID is not valid.")
    if errors:
        raise FisPayloadValidationError(errors)

    payload = {
        "schemaVersion": 1,
        "title": submission["title"],
        "disciplineCode": discipline_code,
        "eventIds": event_ids,
        "sections": sections,
    }
    if expected_version is not None:
        payload["expectedVersion"] = expected_version
    if organisation_uuid:
        payload["organisationUuid"] = organisation_uuid
    return payload
