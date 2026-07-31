"""Read-only importer for official FIS public Alpine result classifications."""

import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from html import unescape
from time import monotonic, sleep


FIS_RESULTS_URL = "https://www.fis-ski.com/DB/general/results.html"


class FisResultError(RuntimeError):
    pass


class _ResultParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.field = None
        self.field_depth = 0
        self.pending_status = "finished"
        self.status_text = None
        self.status_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        if tag == "a" and "table-row" in classes and "athlete-biography.html" in attrs.get("href", ""):
            competitor_id = (parse_qs(urlparse(attrs["href"]).query).get("competitorid") or [""])[0]
            self.row = {"competitor_id": competitor_id, "status": self.pending_status}
            return
        if self.row is not None and tag == "div":
            field = None
            if {"g-lg-1", "pr-1", "bold", "justify-right"}.issubset(classes):
                field = "place"
            elif {"g-lg-1", "gray", "justify-center"}.issubset(classes):
                field = "bib"
            elif {"g-lg-2", "pr-1", "gray", "justify-right"}.issubset(classes):
                field = "fis_code"
            # FIS has used both four- and six-column athlete cells. Keep the
            # semantic class checks but tolerate either historical layout.
            elif ("bold" in classes and "justify-left" in classes
                  and any(re.fullmatch(r"g-lg-\d+", class_name) for class_name in classes)):
                field = "athlete"
            elif {"g-lg-1", "hidden-sm-down", "justify-left"}.issubset(classes):
                field = "birth_year"
            elif {"g-lg-2", "blue", "bold", "justify-right"}.issubset(classes):
                field = "time"
            if field and self.field is None:
                self.field, self.field_depth = field, 1
            elif self.field:
                self.field_depth += 1
        elif self.row is not None and tag == "span" and "country__name-short" in classes:
            self.field, self.field_depth = "nation", 1
        elif tag == "div" and {"g-xs-24", "bold"}.issubset(classes) and self.row is None:
            self.status_text, self.status_depth = [], 1
        elif self.status_text is not None:
            self.status_depth += 1

    def handle_data(self, data):
        value = re.sub(r"\s+", " ", data).strip()
        if value and self.row is not None and self.field:
            self.row[self.field] = f"{self.row.get(self.field, '')} {value}".strip()
        elif value and self.status_text is not None:
            self.status_text.append(value)

    def handle_endtag(self, tag):
        if self.row is not None and self.field and tag in ("div", "span"):
            self.field_depth -= 1
            if self.field_depth <= 0:
                self.field = None
        if self.status_text is not None and tag == "div":
            self.status_depth -= 1
            if self.status_depth <= 0:
                label = " ".join(self.status_text).casefold()
                if "did not qualify" in label:
                    self.pending_status = "did_not_qualify"
                elif "did not finish" in label:
                    self.pending_status = "did_not_finish"
                elif "did not start" in label:
                    self.pending_status = "did_not_start"
                elif "disqualified" in label:
                    self.pending_status = "disqualified"
                self.status_text = None
        if tag == "a" and self.row is not None:
            self.rows.append(self.row)
            self.row = self.field = None


def parse_fis_results(html, race):
    parser = _ResultParser()
    parser.feed(html)
    metadata = dict(race.get("metadata") or {})
    venue_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.I | re.S)
    option_match = re.search(r'<option[^>]*selected[^>]*>\s*\d{2}\.\d{2}\.\d{4}\s*-\s*(.*?)\s*\|\s*([^<]+)</option>', html, re.I | re.S)
    date_match = re.search(r'data-formatted-date="([^"]+)"', html, re.I)
    venue = re.sub(r"\s*\([A-Z]{3}\)\s*$", "", re.sub(r"<[^>]+>", "", unescape(venue_match.group(1))).strip()) if venue_match else ""
    event_name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", unescape(option_match.group(1)))).strip() if option_match else ""
    event_codes = {"Giant Slalom": "GS", "Team Combined": "TC", "Downhill": "DH", "Super G": "SG", "Slalom": "SL"}
    event_code = next((code for label, code in event_codes.items() if label.casefold() in event_name.casefold()), "AL")
    gender = "W" if event_name.casefold().startswith("women") else "M" if event_name.casefold().startswith("men") else ""
    iso_date = ""
    if date_match:
        try:
            iso_date = datetime.strptime(unescape(date_match.group(1)), "%B %d, %Y").date().isoformat()
        except ValueError:
            pass
    imported_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for item in parser.rows:
        fis_code = item.get("fis_code", "").strip()
        athlete = item.get("athlete", "").strip()
        nation = item.get("nation", "").strip().upper()
        # Early World Cup records use stable negative legacy identifiers.
        if not re.fullmatch(r"-?\d+", fis_code) or not athlete or not re.fullmatch(r"[A-Z]{3}", nation):
            continue
        raw_place = item.get("place", "").strip()
        rows.append({
            "race_id": str(race.get("canonical_id") or ""), "date": metadata.get("date") or iso_date,
            "venue": race.get("event_name") or venue or race.get("name") or "FIS event",
            "discipline": metadata.get("event_code") or metadata.get("discipline") or event_code,
            "gender": metadata.get("gender") or gender, "competition": metadata.get("category_code") or (option_match.group(2).strip() if option_match else "FIS"),
            "place": int(raw_place) if raw_place.isdigit() else None, "status": item.get("status", "finished"),
            "athlete": athlete, "fis_code": fis_code, "competitor_id": item.get("competitor_id", ""),
            "nation": nation, "bib": item.get("bib", "").strip(), "birth_year": item.get("birth_year", "").strip(),
            "time": item.get("time", "").strip(), "source_url": race.get("canonical_url") or "",
            "source": "fis_official_results", "imported_at": imported_at,
        })
    return rows


def _fetch_race(race, timeout):
    race_id = str(race.get("canonical_id") or "")
    if not race_id.isdigit():
        raise FisResultError("FIS competition IDs must contain digits only.")
    source_url = f"{FIS_RESULTS_URL}?raceid={race_id}&sectorcode=AL"
    request = Request(source_url, headers={"User-Agent": "CXMS Sports Editorial Pilot/1.0", "Accept": "text/html"})
    with urlopen(request, timeout=timeout) as response:
        html = response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")
    race = {**race, "canonical_url": source_url}
    return parse_fis_results(html, race)


def fetch_alpine_results(races, timeout=20, request_interval=1.5):
    """Fetch a deliberately small batch sequentially, with spacing between FIS calls."""
    if not races or len(races) > 10:
        raise FisResultError("Choose between 1 and 10 FIS competitions per calculation.")
    rows, failures, failure_details = [], 0, []
    previous_request_at = None
    for race in races:
        if previous_request_at is not None:
            remaining = request_interval - (monotonic() - previous_request_at)
            if remaining > 0:
                sleep(remaining)
        previous_request_at = monotonic()
        try:
            rows.extend(_fetch_race(race, timeout))
        except (HTTPError, URLError, TimeoutError, OSError, FisResultError) as exc:
            failures += 1
            race_id = str(race.get("canonical_id") or "unknown")
            reason = f"HTTP {exc.code}" if isinstance(exc, HTTPError) else str(exc) or exc.__class__.__name__
            failure_details.append(f"{race_id}: {reason}")
    if not rows:
        detail = "; ".join(failure_details[:3])
        raise FisResultError(f"No completed classifications were found for this batch.{f' {detail}' if detail else ''}")
    return rows, failures
