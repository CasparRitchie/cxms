import re
from datetime import datetime


MIN_SEASON = 2000
MAX_SEASON = 2100

SPORTS = (
    {"value": "alpine_skiing", "label": "Alpine Skiing", "display_code": "ALP", "enabled": True, "discipline_code": "AL"},
    {"value": "ski_jumping", "label": "Ski Jumping", "display_code": "SJP", "enabled": True, "discipline_code": "JP", "multiple_events": True},
    {"value": "cross_country_skiing", "label": "Cross-Country Skiing", "display_code": "CCS", "enabled": True, "discipline_code": "CC"},
    {"value": "nordic_combined", "label": "Nordic Combined", "display_code": "NCB", "enabled": True, "discipline_code": "NK"},
    {"value": "freestyle", "label": "FRS - Freestyle", "display_code": "FRS", "enabled": True, "discipline_code": "FS", "multiple_events": True, "multiple_genders": True},
    {"value": "freeski_park_and_pipe", "label": "FRS - Freeski P&P", "display_code": "FRS", "enabled": True, "discipline_code": "FS", "multiple_events": True, "multiple_genders": True},
    {"value": "freestyle_ski_cross", "label": "FRS - Ski Cross", "display_code": "FRS", "enabled": True, "discipline_code": "FS"},
    {"value": "snowboard_cross", "label": "SBD - Cross", "display_code": "SBD", "enabled": True, "discipline_code": "SB"},
    {"value": "snowboard_park_and_pipe", "label": "SBD - P&P", "display_code": "SBD", "enabled": True, "discipline_code": "SB", "multiple_events": True, "multiple_genders": True},
    {"value": "snowboard_alpine", "label": "SBD - Alpine", "display_code": "SBD", "enabled": True, "discipline_code": "SB", "multiple_events": True, "multiple_genders": True},
)

COMPETITIONS = {
    "alpine_skiing": (
        "FIS World Cup",
        "FIS World Championships",
    ),
    "ski_jumping": ("FIS World Cup", "FIS Ski Flying World Championships", "FIS World Championships"),
    "cross_country_skiing": ("FIS World Cup", "FIS World Championships"),
    "nordic_combined": ("FIS World Cup", "FIS World Championships"),
    "freestyle": ("FIS World Cup",),
    "freeski_park_and_pipe": ("FIS World Cup",),
    "freestyle_ski_cross": ("FIS World Cup",),
    "snowboard_cross": ("FIS World Cup",),
    "snowboard_park_and_pipe": ("FIS World Cup",),
    "snowboard_alpine": ("FIS World Cup",),
}

def _choices(*items):
    return tuple({"value": name, "label": name, "discipline_code": code, "genders": genders} for name, code, genders in items)


EVENTS = {
    ("alpine_skiing", "FIS World Cup"): _choices(
        ("Slalom", "SL", "MW"), ("Giant Slalom", "GS", "MW"), ("Super G", "SG", "MW"),
        ("Downhill", "DH", "MW"), ("Team Combined", "TC", "MW"), ("Team Parallel", "TP", "X")),
    ("alpine_skiing", "FIS World Championships"): _choices(
        ("Slalom", "SL", "MW"), ("Giant Slalom", "GS", "MW"), ("Super G", "SG", "MW"),
        ("Downhill", "DH", "MW"), ("Team Combined", "TC", "MW"), ("Team Parallel", "TP", "X")),
    ("ski_jumping", "FIS World Cup"): _choices(
        ("Large Hill", "LH", "MW"), ("Normal Hill", "NH", "MW"), ("Flying Hill", "FH", "MW"),
        ("Team Flying Hill", "TF", "M"), ("Super Team Large Hill", "STL", "M"), ("Mixed Team", "TL", "X")),
    ("ski_jumping", "FIS Ski Flying World Championships"): _choices(
        ("Flying Hill", "FH", "M"), ("Team Event", "TF", "M")),
    ("ski_jumping", "FIS World Championships"): _choices(
        ("Large Hill", "LH", "MW"), ("Normal Hill", "NH", "MW"), ("Team Large Hill", "TL", "MX"),
        ("Team Normal Hill", "TN", "WX")),
    ("freestyle", "FIS World Cup"): _choices(("Moguls", "MO", "MW"), ("Aerials", "AE", "MW")),
    ("freeski_park_and_pipe", "FIS World Cup"): _choices(
        ("Slopestyle", "SS", "MW"), ("Halfpipe", "HP", "MW"), ("Big Air", "BA", "MW")),
    ("snowboard_park_and_pipe", "FIS World Cup"): _choices(
        ("Slopestyle", "SS", "MW"), ("Halfpipe", "HP", "MW"), ("Big Air", "BA", "MW")),
    ("snowboard_alpine", "FIS World Cup"): _choices(
        ("Parallel Giant Slalom", "PGS", "MW"), ("Parallel Slalom", "PSL", "MW"),
        ("Giant Slalom", "GS", "MW"), ("Parallel Team", "PRT", "X")),
}

COMPETITION_GENDERS = {
    (sport, competition): ("M", "W", "X") if competition == "FIS World Championships" else ("M", "W")
    for sport in ("cross_country_skiing", "nordic_combined")
    for competition in COMPETITIONS[sport]
}
COMPETITION_GENDERS.update({
    ("freestyle_ski_cross", "FIS World Cup"): ("M", "W"),
    ("snowboard_cross", "FIS World Cup"): ("M", "W"),
})

SPORT_CODES = {item["value"]: item["discipline_code"] for item in SPORTS}
SPORT_DISPLAY_CODES = {item["value"]: item["display_code"] for item in SPORTS}
SPORT_LABELS = {item["value"]: item["label"] for item in SPORTS}
GENDER_LABELS = {"M": "Men", "W": "Women", "X": "Mixed", "O": "Open"}

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
    return {"sports": SPORTS, "competitions": COMPETITIONS, "events": EVENTS, "genders": COMPETITION_GENDERS}


def _as_choices(value):
    if isinstance(value, (list, tuple)):
        return tuple(item for item in value if item)
    return (value,) if value else ()


def allowed_genders(sport, competition, event_name=""):
    choices = EVENTS.get((sport, competition), ())
    if choices:
        selected_values = set(_as_choices(event_name))
        selected = [item for item in choices if item["value"] in selected_values]
        codes = "".join(dict.fromkeys("".join(item["genders"] for item in (selected or choices))))
        return tuple(code for code in ("M", "W", "X") if code in codes)
    return COMPETITION_GENDERS.get((sport, competition), ())


def event_discipline_codes(sport, competition, event_names):
    selected_values = set(_as_choices(event_names))
    return tuple(item["discipline_code"] for item in EVENTS.get((sport, competition), ()) if item["value"] in selected_values)


def event_discipline_code(sport, competition, event_name):
    codes = event_discipline_codes(sport, competition, event_name)
    return codes[0] if codes else None


def validate_choice_combination(sport, competition, event_name, gender=""):
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
    selected_events = _as_choices(event_name)
    selected_genders = _as_choices(gender)
    sport_config = next((item for item in SPORTS if item["value"] == sport), {})
    if allowed_events and not selected_events:
        errors.append("Event is required for the chosen Sport and Competition.")
    if any(item not in {choice["value"] for choice in allowed_events} for item in selected_events):
        errors.append("Select an Event available for the chosen Sport and Competition.")
    if len(selected_events) > 1 and not sport_config.get("multiple_events"):
        errors.append("Select one Event for the chosen Sport.")
    if len(selected_genders) > 1 and not sport_config.get("multiple_genders"):
        errors.append("Select one Gender for the chosen Sport.")
    available_genders = allowed_genders(sport, competition, selected_events)
    if any(item not in available_genders for item in selected_genders):
        errors.append("Select a Gender available for the chosen Sport, Competition and Event.")
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
            "sport": next((sport for sport, code in SPORT_CODES.items() if code == str(metadata.get("discipline_code") or "").upper()), ""),
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
