import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


FIS_CALENDAR_URL = "https://www.fis-ski.com/DB/general/calendar-results.html"


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


def parse_calendar_events(html, source_url, season_code):
    parser = _EventLinkParser()
    parser.feed(html)
    grouped = {}
    for link in parser.links:
        grouped.setdefault(link["event_id"], []).append(link)
    imported_at = datetime.now(timezone.utc).isoformat()
    events = []
    ignored_labels = {"AL", "W", "M", "D", "P", "C", "D P C C"}
    for event_id, links in grouped.items():
        candidates = [item["label"] for item in links if item["label"] and item["label"] not in ignored_labels]
        event_labels = [label for label in candidates if " WC " in f" {label} " and not label.startswith("WC ")]
        descriptive = [label for label in candidates if not re.match(r"^\d{1,2}(?:-|\s)", label) and not re.fullmatch(r"[A-Z]{1,3}(?:\s+[A-Z])?", label)]
        name = max(event_labels or descriptive or candidates, key=len) if candidates else f"FIS Alpine event {event_id}"
        detail_url = urljoin(source_url, links[0]["href"])
        events.append({
            "entity_type": "event",
            "name": name,
            "canonical_id": event_id,
            "canonical_url": detail_url,
            "country_code": "",
            "metadata": {
                "source": "fis_public_calendar",
                "discipline_code": "AL",
                "category_code": "WC",
                "season_code": int(season_code),
                "imported_at": imported_at,
                "source_url": source_url,
            },
        })
    return sorted(events, key=lambda item: (item["name"].casefold(), int(item["canonical_id"])))


def fetch_alpine_world_cup_events(season_code=2027, timeout=20):
    try:
        season = int(season_code)
    except (TypeError, ValueError) as exc:
        raise FisCalendarError("Choose a valid four-digit FIS season.") from exc
    if season < 2000 or season > 2100:
        raise FisCalendarError("Choose a valid four-digit FIS season.")
    params = {
        "categorycode": "WC",
        "seasoncode": str(season),
        "seasonmonth": f"X-{season}",
        "sectorcode": "AL",
        "limit": "100",
    }
    source_url = f"{FIS_CALENDAR_URL}?{urlencode(params)}"
    request = Request(source_url, headers={"User-Agent": "CXMS Sports Editorial Pilot/1.0", "Accept": "text/html"})
    try:
        with urlopen(request, timeout=timeout) as response:
            html = response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")
    except HTTPError as exc:
        raise FisCalendarError(f"FIS calendar returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise FisCalendarError("The public FIS calendar is temporarily unavailable.") from exc
    events = parse_calendar_events(html, source_url, season)
    if not events:
        raise FisCalendarError("No Alpine World Cup events were found. FIS may have changed the calendar page.")
    return events, source_url
