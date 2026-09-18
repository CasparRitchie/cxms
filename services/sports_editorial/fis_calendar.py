import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


FIS_CALENDAR_URL = "https://www.fis-ski.com/DB/general/calendar-results.html"

PUBLIC_CALENDAR_TARGETS = (
    ("AL", "WC", ("alpine_skiing",)),
    ("AL", "WSC", ("alpine_skiing",)),
    ("JP", "WC", ("ski_jumping",)),
    ("JP", "WSC", ("ski_jumping",)),
    ("CC", "WC", ("cross_country_skiing",)),
    ("CC", "WSC", ("cross_country_skiing",)),
    ("NK", "WC", ("nordic_combined",)),
    ("NK", "WSC", ("nordic_combined",)),
    ("FS", "WC", ("freestyle", "freeski_park_and_pipe", "freestyle_ski_cross")),
    ("SB", "WC", ("snowboard_cross", "snowboard_park_and_pipe", "snowboard_alpine")),
)


class FisCalendarError(RuntimeError):
    pass


class _EventLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href", "")
        query = parse_qs(urlparse(href).query)
        event_id = (query.get("eventid") or [""])[0]
        if "event-details.html" in href and event_id.isdigit():
            self.current = {"event_id": event_id, "href": href, "text": []}

    def handle_data(self, data):
        if self.current:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current:
            self.current["label"] = re.sub(r"\s+", " ", "".join(self.current["text"])).strip()
            self.links.append(self.current)
            self.current = None


def _calendar_sports(name, discipline_code, fallback_sports):
    """Narrow shared FS/SB calendars using the event codes published by FIS."""
    codes = set(re.findall(r"(?<![A-Z])(?:\d+X)?([A-Z]{2,3})(?![A-Z])", name.upper()))
    if discipline_code == "FS":
        sports = []
        if codes & {"MO", "DM", "AE", "AET", "DMT"}:
            sports.append("freestyle")
        if codes & {"SS", "HP", "BA", "ST"}:
            sports.append("freeski_park_and_pipe")
        if codes & {"SX", "SXT"}:
            sports.append("freestyle_ski_cross")
        return tuple(sports) or tuple(fallback_sports)
    if discipline_code == "SB":
        sports = []
        if codes & {"SBX", "SX", "SXT"}:
            sports.append("snowboard_cross")
        if codes & {"SS", "HP", "BA", "ST"}:
            sports.append("snowboard_park_and_pipe")
        if codes & {"PGS", "PSL", "GS", "PRT"}:
            sports.append("snowboard_alpine")
        return tuple(sports) or tuple(fallback_sports)
    return tuple(fallback_sports)


def parse_calendar_events(html, source_url, season_code, discipline_code="AL", category_code="WC", sport_values=None):
    parser = _EventLinkParser()
    parser.feed(html)
    grouped = {}
    for link in parser.links:
        grouped.setdefault(link["event_id"], []).append(link)
    imported_at = datetime.now(timezone.utc).isoformat()
    events = []
    discipline_code = str(discipline_code or "").upper()
    category_code = str(category_code or "").upper()
    sport_values = tuple(sport_values or ("alpine_skiing",))
    ignored_labels = {discipline_code, "W", "M", "X", "D", "P", "C", "D P C C"}
    for event_id, links in grouped.items():
        candidates = [item["label"] for item in links if item["label"] and item["label"] not in ignored_labels]
        event_labels = [label for label in candidates if f" {category_code} " in f" {label} " and not label.startswith(f"{category_code} ")]
        descriptive = [label for label in candidates if not re.match(r"^\d{1,2}(?:-|\s)", label) and not re.fullmatch(r"[A-Z]{1,3}(?:\s+[A-Z])?", label)]
        name = max(event_labels or descriptive or candidates, key=len) if candidates else f"FIS {discipline_code} event {event_id}"
        location_label = re.split(rf"\s+{re.escape(category_code)}(?:\s|$)", name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        detail_url = urljoin(source_url, links[0]["href"])
        events.append({
            "entity_type": "event",
            "name": name,
            "canonical_id": event_id,
            "canonical_url": detail_url,
            "country_code": "",
            "metadata": {
                "source": "fis_public_calendar",
                "discipline_code": discipline_code,
                "category_code": category_code,
                "sport_values": list(_calendar_sports(name, discipline_code, sport_values)),
                "location_label": location_label or name,
                "season_code": int(season_code),
                "imported_at": imported_at,
                "source_url": source_url,
            },
        })
    return sorted(events, key=lambda item: (item["name"].casefold(), int(item["canonical_id"])))


def fetch_alpine_world_cup_events(season_code=2027, timeout=20):
    events, source_urls = fetch_public_calendar_events(
        season_code, timeout=timeout, targets=(("AL", "WC", ("alpine_skiing",)),)
    )
    return events, source_urls[0]


def _merge_calendar_events(events):
    merged = {}
    for event in events:
        event_id = event["canonical_id"]
        existing = merged.get(event_id)
        if not existing:
            merged[event_id] = event
            continue
        existing_sports = list((existing.get("metadata") or {}).get("sport_values") or [])
        incoming_sports = (event.get("metadata") or {}).get("sport_values") or []
        existing["metadata"]["sport_values"] = list(dict.fromkeys(existing_sports + list(incoming_sports)))
        if len(event.get("name", "")) > len(existing.get("name", "")):
            existing["name"] = event["name"]
    return sorted(merged.values(), key=lambda item: (item["name"].casefold(), int(item["canonical_id"])))


def fetch_public_calendar_events(season_code=2027, timeout=20, targets=PUBLIC_CALENDAR_TARGETS):
    try:
        season = int(season_code)
    except (TypeError, ValueError) as exc:
        raise FisCalendarError("Choose a valid four-digit FIS season.") from exc
    if season < 1967 or season > 2100:
        raise FisCalendarError("Choose a FIS season from 1967 onwards.")
    def fetch_target(target):
        discipline_code, category_code, sport_values = target
        params = {
            "categorycode": category_code,
            "seasoncode": str(season),
            "seasonmonth": f"X-{season}",
            "sectorcode": discipline_code,
            "limit": "100",
        }
        source_url = f"{FIS_CALENDAR_URL}?{urlencode(params)}"
        request = Request(source_url, headers={"User-Agent": "CXMS Sports Editorial Pilot/1.0", "Accept": "text/html"})
        try:
            with urlopen(request, timeout=timeout) as response:
                html = response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")
        except HTTPError as exc:
            return [], "", f"{discipline_code}/{category_code} returned HTTP {exc.code}"
        except (URLError, TimeoutError):
            return [], "", f"{discipline_code}/{category_code} was unavailable"
        parsed = parse_calendar_events(
            html, source_url, season, discipline_code=discipline_code,
            category_code=category_code, sport_values=sport_values,
        )
        return parsed, source_url, ""

    events = []
    source_urls = []
    failures = []
    targets = tuple(targets)
    with ThreadPoolExecutor(max_workers=min(5, len(targets))) as executor:
        futures = [executor.submit(fetch_target, target) for target in targets]
        for future in as_completed(futures):
            parsed, source_url, failure = future.result()
            events.extend(parsed)
            if source_url:
                source_urls.append(source_url)
            if failure:
                failures.append(failure)
    events = _merge_calendar_events(events)
    if not events:
        detail = f" ({'; '.join(failures)})" if failures else ""
        raise FisCalendarError(f"No supported FIS calendar events were found. FIS may have changed the calendar page.{detail}")
    return events, source_urls
