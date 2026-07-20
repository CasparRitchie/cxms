VALID_STATUSES = ("draft", "submitted", "in_review", "changes_requested", "approved", "exported")
VALID_ENTITY_TYPES = ("athlete", "country", "event", "competition")
VALID_CONTENT_TYPES = ("stat", "section", "heading")

from .formatting import rich_text_to_plain

STATUS_TRANSITIONS = {
    "draft": {"draft", "submitted"},
    "submitted": {"submitted", "in_review", "changes_requested", "approved"},
    "in_review": {"in_review", "changes_requested", "approved"},
    "changes_requested": {"changes_requested", "submitted", "in_review"},
    "approved": {"approved", "exported", "in_review"},
    "exported": {"exported", "approved"},
}


def validate_submission(data, submitting=False):
    errors = []
    if not str(data.get("title", "")).strip():
        errors.append("Add a title for this stat pack.")
    content = data.get("content", [])
    if not content and data.get("stats"):
        content = [{"content_type": "stat", "content_html": item} for item in data["stats"]]
    valid_blocks = [item for item in content if item.get("content_type") in VALID_CONTENT_TYPES and rich_text_to_plain(item.get("content_html"))]
    stats = [item for item in valid_blocks if item["content_type"] == "stat"]
    if not stats:
        errors.append("Add at least one statistic.")
    if submitting and valid_blocks and len(valid_blocks) != len(content):
        errors.append("Remove or complete empty content blocks before submitting.")
    return errors


def validate_status_transition(current, requested):
    if requested not in VALID_STATUSES:
        return False, "That status is not available."
    if requested not in STATUS_TRANSITIONS.get(current, set()):
        return False, f"A submission cannot move from {current.replace('_', ' ')} to {requested.replace('_', ' ')}."
    return True, ""
