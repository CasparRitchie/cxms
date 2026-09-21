from collections import Counter
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from .race_status import effective_race_status


WORKFLOW_GROUPS = (
    ("in_progress", "In Progress", ("draft", "changes_requested")),
    ("in_sub_edit", "In Sub Edit", ("submitted", "in_review")),
    ("approved", "Approved", ("approved",)),
    ("fis_review", "Awaiting FIS Review", ("fis_review",)),
    ("exported", "Published FIS", ("exported",)),
)

COVERAGE_RANGE_OPTIONS = (
    ("this_week", "This week"),
    ("next_week", "Next week"),
    ("next_14_days", "Next 14 days"),
    ("next_30_days", "Next 30 days"),
    ("this_month", "This month"),
    ("next_month", "Next month"),
    ("this_year", "This year"),
    ("next_year", "Next year"),
    ("next_12_months", "Next 12 months"),
    ("custom", "Custom dates"),
)


def resolve_coverage_range(preset="next_14_days", start=None, end=None, today=None):
    today = today or datetime.now(timezone.utc).date()
    option_keys = {key for key, _label in COVERAGE_RANGE_OPTIONS}
    preset = preset if preset in option_keys else "next_14_days"
    if preset == "custom":
        custom_start, custom_end = _as_date(start), _as_date(end)
        if custom_start and custom_end and custom_start <= custom_end:
            return custom_start, custom_end, preset
        preset = "next_14_days"
    if preset == "this_week":
        return today, today + timedelta(days=6 - today.weekday()), preset
    if preset == "next_week":
        next_monday = today + timedelta(days=7 - today.weekday())
        return next_monday, next_monday + timedelta(days=6), preset
    if preset == "this_month":
        return today, date(today.year, today.month, monthrange(today.year, today.month)[1]), preset
    if preset == "next_month":
        year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        return date(year, month, 1), date(year, month, monthrange(year, month)[1]), preset
    if preset == "this_year":
        return today, date(today.year, 12, 31), preset
    if preset == "next_year":
        return date(today.year + 1, 1, 1), date(today.year + 1, 12, 31), preset
    days = {"next_14_days": 14, "next_30_days": 30, "next_12_months": 365}.get(preset, 14)
    return today, today + timedelta(days=days), preset


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


def _id_values(item, field):
    return {str(value) for value in item.get(field) or [] if str(value)}


def _workflow_counts(submissions):
    return {
        key: sum(item.get("status") in statuses for item in submissions)
        for key, _label, statuses in WORKFLOW_GROUPS
    }


def _fis_coverage(active, events, competitions, range_start, range_end):
    races = []
    races_by_event = {}
    for competition in competitions:
        metadata = competition.get("metadata") or {}
        if str(metadata.get("competition_kind") or "race").casefold() in ("training", "qualification"):
            continue
        race_date = _as_date(metadata.get("date"))
        if not race_date or not range_start <= race_date <= range_end:
            continue
        race_id = str(competition.get("canonical_id") or "")
        event_id = str(metadata.get("event_id") or "")
        status, status_source = effective_race_status(competition)
        linked = [sheet for sheet in active if race_id in _id_values(sheet, "fis_race_ids")]
        row = {
            **competition,
            "race_id": race_id,
            "event_id": event_id,
            "race_date": race_date.isoformat(),
            "days_until": (race_date - range_start).days,
            "race_status": status,
            "race_status_source": status_source,
            "stat_sheets": linked,
            "stat_sheet_count": len(linked),
            "workflow_counts": _workflow_counts(linked),
            "is_missing": status != "cancelled" and not linked,
        }
        races.append(row)
        races_by_event.setdefault(event_id, []).append(row)
    races.sort(key=lambda item: (item["race_date"], item["event_id"], item["race_id"]))

    event_entities = {str(item.get("canonical_id") or ""): item for item in events}
    event_ids = set(races_by_event)
    for event_id, event in event_entities.items():
        metadata = event.get("metadata") or {}
        start = _as_date(metadata.get("start_date"))
        end = _as_date(metadata.get("end_date")) or start
        if start and end and start <= range_end and end >= range_start:
            event_ids.add(event_id)

    event_rows = []
    for event_id in event_ids:
        event = event_entities.get(event_id, {})
        metadata = event.get("metadata") or {}
        event_races = races_by_event.get(event_id, [])
        start = _as_date(metadata.get("start_date"))
        end = _as_date(metadata.get("end_date")) or start
        if not start and event_races:
            start = _as_date(event_races[0]["race_date"])
            end = _as_date(event_races[-1]["race_date"])
        linked = [sheet for sheet in active if event_id in _id_values(sheet, "fis_event_ids")]
        scheduled_races = [race for race in event_races if race["race_status"] != "cancelled"]
        is_cancelled = bool(event_races) and not scheduled_races
        event_rows.append({
            **event,
            "event_id": event_id,
            "location": metadata.get("location_label") or event.get("name") or "FIS event",
            "start_date": start.isoformat() if start else "",
            "end_date": end.isoformat() if end else "",
            "discipline_code": metadata.get("discipline_code") or "",
            "category_code": metadata.get("category_code") or "",
            "race_count": len(event_races),
            "scheduled_race_count": len(scheduled_races),
            "cancelled_race_count": len(event_races) - len(scheduled_races),
            "stat_sheets": linked,
            "stat_sheet_count": len(linked),
            "workflow_counts": _workflow_counts(linked),
            "is_cancelled": is_cancelled,
            "is_missing": not is_cancelled and not linked,
        })
    event_rows.sort(key=lambda item: (item["start_date"] or "9999-12-31", item["location"], item["event_id"]))

    scheduled_races = [race for race in races if race["race_status"] != "cancelled"]
    covered_races = [race for race in scheduled_races if race["stat_sheet_count"]]
    relevant_events = [event for event in event_rows if not event["is_cancelled"]]
    covered_events = [event for event in relevant_events if event["stat_sheet_count"]]
    return {
        "events": event_rows,
        "races": races,
        "summary": {
            "events": len(relevant_events),
            "covered_events": len(covered_events),
            "missing_events": sum(event["is_missing"] for event in relevant_events),
            "event_coverage_percent": round(len(covered_events) / len(relevant_events) * 100) if relevant_events else 0,
            "races": len(scheduled_races),
            "covered_races": len(covered_races),
            "missing_races": sum(race["is_missing"] for race in scheduled_races),
            "race_coverage_percent": round(len(covered_races) / len(scheduled_races) * 100) if scheduled_races else 0,
            "cancelled_races": len(races) - len(scheduled_races),
        },
    }


def build_dashboard_metrics(submissions, users, events=None, competitions=None, today=None, upcoming_days=14,
                            coverage_start=None, coverage_end=None, coverage_preset="next_14_days"):
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
    coverage_start = _as_date(coverage_start) or today
    coverage_end = _as_date(coverage_end) or upcoming_end
    if coverage_end < coverage_start:
        coverage_start, coverage_end = today, upcoming_end
        coverage_preset = "next_14_days"
    fis_coverage = _fis_coverage(active, events or [], competitions or [], coverage_start, coverage_end)
    fis_coverage["range"] = {
        "start": coverage_start.isoformat(), "end": coverage_end.isoformat(),
        "preset": coverage_preset,
    }
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
        "fis_coverage": fis_coverage,
        "breakdowns": {
            "researchers": _rank(active, "researcher_name"),
            "sub_editors": _rank(active, "sub_editor_name"),
            "events": _rank(active, "event_name", "No event"),
            "locations": _rank(active, "location", "No location"),
            "seasons": _rank(active, "season_code", "No season"),
        },
        "user_roles": _rank(active_users, "editorial_role", "No role"),
    }
