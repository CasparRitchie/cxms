import re
import unicodedata


def _slug(value, fallback):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or fallback


def build_fis_external_id(data):
    """Build the stable, readable AMP identifier agreed for the ALP pilot."""
    gender = str(data.get("gender") or "u").lower()
    event = _slug(data.get("event_name"), "event")
    location = _slug(data.get("location"), "location")
    date = str(data.get("event_date") or "")
    year = date[:4] if len(date) >= 4 and date[:4].isdigit() else "undated"
    return f"amp-alp-{gender}-{event}-{location}-{year}"[:255]
