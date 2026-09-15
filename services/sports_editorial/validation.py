VALID_STATUSES = ("draft", "submitted", "in_review", "changes_requested", "approved", "fis_review", "exported")
ACTIVE_STATUSES = ("draft", "in_review", "approved", "fis_review", "exported")
VALID_ENTITY_TYPES = ("athlete", "country", "event", "competition")
VALID_CONTENT_TYPES = ("stat", "section", "heading")
STATUS_LABELS = {"draft": "In Progress", "submitted": "In Sub Edit", "in_review": "In Sub Edit", "changes_requested": "In Progress", "approved": "Approved", "fis_review": "Awaiting FIS Review", "exported": "Published FIS"}

from .formatting import rich_text_to_plain

STATUS_TRANSITIONS = {
    "draft": {"draft", "in_review"},
    "submitted": {"submitted", "in_review", "changes_requested", "approved", "fis_review"},
    "in_review": {"in_review", "draft", "approved", "fis_review"},
    "changes_requested": {"changes_requested", "submitted", "in_review"},
    "approved": {"approved", "fis_review", "in_review", "draft"},
    "fis_review": {"fis_review", "in_review", "exported"},
    "exported": {"exported", "in_review", "draft"},
}

MAX_TITLE_CHARACTERS = 160
MAX_STAT_CHARACTERS = 5000
MAX_CONTENT_BLOCKS = 200
MAX_WORKING_NOTES_CHARACTERS = 10000
MAX_UNUSED_STATS_CHARACTERS = 2500


def validate_editorial_limits(data):
    errors = []
    title = str(data.get("title") or "")
    if len(title) > MAX_TITLE_CHARACTERS:
        errors.append(f"Title must be {MAX_TITLE_CHARACTERS} characters or fewer.")
    content = data.get("content") or []
    valid_blocks = [item for item in content if item.get("content_type") in VALID_CONTENT_TYPES and rich_text_to_plain(item.get("content_html"))]
    if len(valid_blocks) > MAX_CONTENT_BLOCKS:
        errors.append(f"A stat sheet can contain no more than {MAX_CONTENT_BLOCKS} content blocks.")
    if any(item.get("content_type") == "stat" and len(rich_text_to_plain(item.get("content_html"))) > MAX_STAT_CHARACTERS for item in valid_blocks):
        errors.append(f"Each statistic must be {MAX_STAT_CHARACTERS:,} characters or fewer.")
    if len(str(data.get("working_notes") or "")) > MAX_WORKING_NOTES_CHARACTERS:
        errors.append(f"Working Notes must be {MAX_WORKING_NOTES_CHARACTERS:,} characters or fewer.")
    if len(str(data.get("unused_stats") or "")) > MAX_UNUSED_STATS_CHARACTERS:
        errors.append(f"Unused Stats must be {MAX_UNUSED_STATS_CHARACTERS:,} characters or fewer.")
    return errors


def validate_submission(data, submitting=False):
    errors = validate_editorial_limits(data)
    if not str(data.get("title", "")).strip():
        errors.append("Add a title for this stat sheet.")
    content = data.get("content", [])
    if not content and data.get("stats"):
        content = [{"content_type": "stat", "content_html": item} for item in data["stats"]]
    valid_blocks = [item for item in content if item.get("content_type") in VALID_CONTENT_TYPES and rich_text_to_plain(item.get("content_html"))]
    stats = [item for item in valid_blocks if item["content_type"] == "stat"]
    if not stats:
        errors.append("Add at least one statistic.")
    if submitting and valid_blocks and len(valid_blocks) != len(content):
        errors.append("Remove or complete empty content blocks before submitting.")
    event_ids = data.get("fis_event_ids") or []
    # A calendar event may be allocated by a Supervisor during Sub Edit. The
    # approval/publishing routes remain authoritative and reject a missing ID.
    if len(event_ids) > 10:
        errors.append("Select no more than 10 FIS calendar events.")
    return errors


def validate_status_transition(current, requested):
    if requested not in VALID_STATUSES:
        return False, "That status is not available."
    if requested not in STATUS_TRANSITIONS.get(current, set()):
        return False, f"A submission cannot move from {current.replace('_', ' ')} to {requested.replace('_', ' ')}."
    return True, ""
