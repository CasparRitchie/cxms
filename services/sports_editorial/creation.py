import re
from datetime import datetime


MIN_SEASON = 2000
MAX_SEASON = 2100

# ALP is the only creatable sport today. Enabling CCS or SJP also requires
# schema, validation, catalogue, export, and publishing support.
SPORTS = (
    {"value": "alpine_skiing", "label": "Alpine Skiing (ALP)", "enabled": True, "discipline_code": "AL"},
    {"value": "cross_country_skiing", "label": "Cross-Country Skiing (CCS) — Coming soon", "enabled": False, "discipline_code": "CC"},
    {"value": "ski_jumping", "label": "Ski Jumping (SJP) — Coming soon", "enabled": False, "discipline_code": "JP"},
)

COMPETITIONS = {
    "alpine_skiing": (
        "FIS World Cup",
        "FIS World Championships",
        "FIS Junior World Championships",
    ),
}

EVENTS = {
    ("alpine_skiing", "FIS World Cup"): (
        "Downhill",
        "Giant Slalom",
        "Slalom",
        "Super G",
    ),
}

COMPETITION_CATEGORY_CODES = {
    "FIS World Cup": {"WC"},
    "FIS World Championships": {"WSC"},
    "FIS Junior World Championships": {"WJC"},
}

_LOCAL_EVENT_OVERRIDES = {
    "55596": {"location_label": "Kronplatz", "competition": "FIS World Cup"},
    "55595": {"location_label": "Kranjska Gora", "competition": "FIS World Cup"},
}


def creation_options():
    return {"sports": SPORTS, "competitions": COMPETITIONS, "events": EVENTS}


def validate_choice_combination(sport, competition, event_name):
    errors = []
    enabled_sports = {item["value"] for item in SPORTS if item["enabled"]}
    if not sport.strip():
        errors.append("Sport is required.")
    elif sport not in enabled_sports:
        errors.append("Select a supported Sport.")
    if not competition.strip():
        errors.append("Competition is required.")
    elif competition not in COMPETITIONS.get(sport, ()):
        errors.append("Select a Competition available for the chosen Sport.")
    allowed_events = EVENTS.get((sport, competition), ())
    if event_name and event_name not in allowed_events:
        errors.append("Select an Event available for the chosen Sport and Competition.")
    return errors


def parse_display_date(value, field_label):
    raw = (value or "").strip()
    if not raw:
        return "", None
    try:
        parsed = datetime.strptime(raw.title(), "%d-%b-%Y").date()
    except ValueError:
        return "", f"{field_label} must be a real date in DD-MMM-YYYY format."
    if parsed.strftime("%d-%b-%Y").casefold() != raw.casefold():
        return "", f"{field_label} must use DD-MMM-YYYY, not a numeric or ambiguous format."
    return parsed.isoformat(), None


def format_display_date(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%d-%b-%Y")
    except ValueError:
        return raw


def _metadata(event):
    return event.get("metadata") or {}


def _calendar_location_label(event):
    """Return a maintained canonical location label for a calendar event.

    Imported calendar rows historically stored the complete event label in
    ``name``. New imports should provide ``metadata.location_label``; this
    conservative fallback keeps existing rows usable without asking templates
    to parse FIS display strings.
    """
    canonical_id = str(event.get("canonical_id") or "")
    metadata = _metadata(event)
    override = _LOCAL_EVENT_OVERRIDES.get(canonical_id, {})
    if override.get("location_label"):
        return override["location_label"]
    if str(metadata.get("location_label") or "").strip():
        return str(metadata["location_label"]).strip()
    name = str(event.get("name") or "").strip()
    world_cup_location = re.split(r"\s+WC(?:\s|$)", name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return world_cup_location or name


def canonical_calendar_events(events):
    catalogue = []
    for event in events:
        canonical_id = str(event.get("canonical_id") or "")
        if not canonical_id.isdigit():
            continue
        metadata = _metadata(event)
        override = _LOCAL_EVENT_OVERRIDES.get(canonical_id, {})
        location = _calendar_location_label(event)
        competition = override.get("competition")
        if not competition:
            category = str(metadata.get("category_code") or "").upper()
            competition = next((name for name, codes in COMPETITION_CATEGORY_CODES.items() if category in codes), "")
        catalogue.append({
            "canonical_id": canonical_id,
            "location": location,
            "label": f"{event.get('name', '').strip() or location} — {canonical_id}",
            "search_text": " ".join((location, event.get("name", ""), canonical_id)).strip(),
            "sport": "alpine_skiing" if str(metadata.get("discipline_code") or "").upper() == "AL" else "",
            "competition": competition,
            "season_code": metadata.get("season_code"),
        })
    return catalogue


def resolve_calendar_event(events, canonical_id, sport, competition, season_code):
    event = next((item for item in canonical_calendar_events(events) if item["canonical_id"] == str(canonical_id or "")), None)
    if not event:
        return None, "Select a known Client Event ID from the local calendar catalogue."
    if event["sport"] != sport or event["competition"] != competition or event["season_code"] != season_code:
        return None, "The selected calendar event is not compatible with Sport, Competition and Season."
    return event, None
