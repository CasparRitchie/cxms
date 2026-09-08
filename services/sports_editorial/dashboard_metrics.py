from collections import Counter
from datetime import date, datetime, timedelta, timezone


WORKFLOW_GROUPS = (
    ("in_progress", "In Progress", ("draft", "changes_requested")),
    ("in_sub_edit", "In Sub Edit", ("submitted", "in_review")),
    ("approved", "Approved (legacy)", ("approved",)),
    ("fis_review", "Awaiting FIS Review", ("fis_review",)),
    ("exported", "Published FIS", ("exported",)),
)


def _as_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _rank(submissions, field, fallback="Unassigned", limit=8):
    counts = Counter(str(item.get(field) or fallback) for item in submissions)
    return [{"label": label, "count": count} for label, count in counts.most_common(limit)]


def build_dashboard_metrics(submissions, users, today=None, upcoming_days=14):
    """Build the management snapshot without making additional data requests."""
    today = today or datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=today.weekday())
    upcoming_end = today + timedelta(days=upcoming_days)
    active = [item for item in submissions if item.get("is_active", True)]

    workflow = []
    for key, label, statuses in WORKFLOW_GROUPS:
        count = sum(item.get("status") in statuses for item in active)
        workflow.append({
            "key": key, "label": label, "statuses": statuses, "count": count,
            "percent": round((count / len(active)) * 100) if active else 0,
        })

    upcoming = []
    for item in active:
        race_date = _as_date(item.get("event_date"))
        if race_date and today <= race_date <= upcoming_end:
            upcoming.append({**item, "days_until": (race_date - today).days})
    upcoming.sort(key=lambda item: (item.get("event_date") or "", item.get("location") or ""))

    completed_this_week = sum(
        item.get("status") == "exported" and (_as_date(item.get("updated_at")) or date.min) >= week_start
        for item in active
    )
    cancelled = [item for item in active if item.get("race_status") == "cancelled"]
    cancelled_this_week = sum(
        (_as_date(item.get("updated_at")) or date.min) >= week_start for item in cancelled
    )
    unallocated = [item for item in active if not item.get("researcher_user_id")]
    pending_upcoming = [item for item in upcoming if item.get("status") != "exported"]

    attention = []
    for item in active:
        race_date = _as_date(item.get("event_date"))
        researcher_deadline = _as_date(item.get("researcher_deadline"))
        publication_deadline = _as_date(item.get("publication_deadline"))
        reasons = []
        if not item.get("researcher_user_id"):
            reasons.append("No researcher")
        if researcher_deadline and researcher_deadline < today and item.get("status") in ("draft", "changes_requested"):
            reasons.append("Research deadline passed")
        if publication_deadline and publication_deadline < today and item.get("status") != "exported":
            reasons.append("Publication deadline passed")
        if race_date and today <= race_date <= upcoming_end and item.get("status") != "exported":
            reasons.append(f"Race in {(race_date - today).days} days")
        if not item.get("fis_event_ids"):
            reasons.append("Missing Client Event ID")
        if reasons:
            attention.append({**item, "attention_reasons": reasons})
    attention.sort(key=lambda item: (item.get("event_date") or "9999-12-31", item.get("title") or ""))

    active_users = [user for user in users if user.get("editorial_is_active", user.get("is_active", True))]
    return {
        "generated_on": today.isoformat(), "upcoming_days": upcoming_days,
        "summary": {
            "total": len(active), "upcoming": len(upcoming), "pending_upcoming": len(pending_upcoming),
            "fis_review": next(item["count"] for item in workflow if item["key"] == "fis_review"),
            "completed_this_week": completed_this_week, "unallocated": len(unallocated),
            "cancelled": len(cancelled), "cancelled_this_week": cancelled_this_week,
            "users": len(active_users),
        },
        "workflow": workflow, "upcoming": upcoming[:20], "attention": attention[:20],
        "breakdowns": {
            "researchers": _rank(active, "researcher_name"),
            "sub_editors": _rank(active, "sub_editor_name"),
            "events": _rank(active, "event_name", "No event"),
            "locations": _rank(active, "location", "No location"),
            "seasons": _rank(active, "season_code", "No season"),
        },
        "user_roles": _rank(active_users, "editorial_role", "No role"),
    }
