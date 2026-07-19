VALID_STATUSES = ("draft", "submitted", "in_review", "changes_requested", "approved", "exported")
VALID_ENTITY_TYPES = ("athlete", "country", "event", "competition")

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
    if not str(data.get("author_name", "")).strip():
        errors.append("Add the journalist's name.")
    stats = [str(item).strip() for item in data.get("stats", [])]
    non_empty = [item for item in stats if item]
    if not non_empty:
        errors.append("Add at least one statistic.")
    if submitting and non_empty and len(non_empty) != len(stats):
        errors.append("Remove or complete empty bullet points before submitting.")
    return errors


def validate_status_transition(current, requested):
    if requested not in VALID_STATUSES:
        return False, "That status is not available."
    if requested not in STATUS_TRANSITIONS.get(current, set()):
        return False, f"A submission cannot move from {current.replace('_', ' ')} to {requested.replace('_', ' ')}."
    return True, ""
