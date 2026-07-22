import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


FIS_NATION_NAMES = {
    "ALB": "Albania", "AND": "Andorra", "ARG": "Argentina", "ARM": "Armenia",
    "AUS": "Australia", "AUT": "Austria", "BEL": "Belgium", "BIH": "Bosnia and Herzegovina",
    "BLR": "Belarus", "BOL": "Bolivia", "BRA": "Brazil", "BUL": "Bulgaria",
    "CAN": "Canada", "CHI": "Chile", "CHN": "China", "COL": "Colombia",
    "CRO": "Croatia", "CYP": "Cyprus", "CZE": "Czechia", "DEN": "Denmark",
    "ECU": "Ecuador", "ESP": "Spain", "EST": "Estonia", "FIN": "Finland",
    "FRA": "France", "GBR": "Great Britain", "GEO": "Georgia", "GER": "Germany",
    "GRE": "Greece", "HUN": "Hungary", "IND": "India", "IRI": "Iran",
    "IRL": "Ireland", "ISL": "Iceland", "ISR": "Israel", "ITA": "Italy",
    "JPN": "Japan", "KAZ": "Kazakhstan", "KGZ": "Kyrgyzstan", "KOR": "South Korea",
    "KOS": "Kosovo", "LAT": "Latvia", "LBN": "Lebanon", "LIE": "Liechtenstein",
    "LTU": "Lithuania", "LUX": "Luxembourg", "MAR": "Morocco", "MDA": "Moldova",
    "MEX": "Mexico", "MKD": "North Macedonia", "MNE": "Montenegro", "MON": "Monaco",
    "MGL": "Mongolia", "NED": "Netherlands", "NOR": "Norway", "NZL": "New Zealand",
    "PAK": "Pakistan", "PER": "Peru", "POL": "Poland", "POR": "Portugal",
    "ROU": "Romania", "RSA": "South Africa", "RUS": "Russia", "SLO": "Slovenia",
    "SRB": "Serbia", "SUI": "Switzerland", "SVK": "Slovakia", "SWE": "Sweden",
    "THA": "Thailand", "TPE": "Chinese Taipei", "TUR": "Türkiye", "UAE": "United Arab Emirates",
    "UKR": "Ukraine", "URU": "Uruguay", "USA": "United States", "UZB": "Uzbekistan",
}


class FisEntityError(RuntimeError):
    pass


def countries_from_athletes(athletes):
    imported_at = datetime.now(timezone.utc).isoformat()
    codes = sorted({item.get("country_code", "").strip().upper() for item in athletes if item.get("country_code")})
    return [{
        "entity_type": "country",
        "name": FIS_NATION_NAMES.get(code, f"{code} (FIS nation code)"),
        "canonical_id": code,
        "canonical_url": "",
        "country_code": code,
        "metadata": {"source": "fis_official_points_list", "discipline_code": "AL", "imported_at": imported_at},
    } for code in codes]


class _RaceLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current = None
        self.races = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.current and attrs.get("data-date"):
            self.current["dates"].append(attrs["data-date"])
        if tag != "a":
            return
        href = attrs.get("href", "")
        race_id = (parse_qs(urlparse(href).query).get("raceid") or [""])[0]
        if race_id.isdigit():
            race = self.races.setdefault(race_id, {"href": href, "labels": [], "dates": []})
            self.current = race

    def handle_data(self, data):
        if self.current:
            value = re.sub(r"\s+", " ", data).strip()
            if value:
                self.current["labels"].append(value)

    def handle_endtag(self, tag):
        if tag == "a":
            self.current = None


def parse_event_competitions(html, event):
    parser = _RaceLinkParser()
    parser.feed(html)
    imported_at = datetime.now(timezone.utc).isoformat()
    competitions = []
    ignored = {"FIS", "C", "P", "D", "No changes", "Not cancelled"}
    for race_id, race in parser.races.items():
        labels = list(dict.fromkeys(label for label in race["labels"] if label not in ignored))
        codex = next((label for label in labels if re.fullmatch(r"\d{4}", label)), "")
        gender = next((label for label in labels if label in ("M", "W")), "")
        discipline = next((label for label in labels if re.search(r"[A-Za-z]", label) and label not in (gender,) and not label.startswith("Replaces ") and not re.match(r"^\d{1,2} [A-Z][a-z]{2}$", label)), "Race")
        date = next(iter(race["dates"]), "")
        name = " · ".join(part for part in (discipline, gender, event.get("name", ""), date, f"codex {codex}" if codex else "") if part)
        competitions.append({
            "entity_type": "competition", "name": name, "canonical_id": race_id,
            "canonical_url": race["href"], "country_code": event.get("country_code", ""),
            "metadata": {"source": "fis_public_event_page", "discipline_code": "AL", "event_id": event.get("canonical_id"),
                         "season_code": (event.get("metadata") or {}).get("season_code"),
                         "category_code": (event.get("metadata") or {}).get("category_code"),
                         "codex": codex, "gender": gender, "date": date or None, "imported_at": imported_at},
        })
    return competitions


def _fetch_event_competitions(event, timeout):
    request = Request(event["canonical_url"], headers={"User-Agent": "CXMS Sports Editorial Pilot/1.0", "Accept": "text/html"})
    with urlopen(request, timeout=timeout) as response:
        html = response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")
    return parse_event_competitions(html, event)


def fetch_alpine_competitions(events, timeout=20, workers=6):
    sources = [event for event in events if str(event.get("canonical_id") or "").isdigit() and event.get("canonical_url")]
    if not sources:
        raise FisEntityError("Import FIS calendar events before refreshing competitions.")
    competitions, failures = [], 0
    with ThreadPoolExecutor(max_workers=min(workers, len(sources))) as pool:
        futures = {pool.submit(_fetch_event_competitions, event, timeout): event for event in sources}
        for future in as_completed(futures):
            try:
                competitions.extend(future.result())
            except (HTTPError, URLError, TimeoutError, OSError):
                failures += 1
    if not competitions:
        raise FisEntityError("No competitions could be read from the imported FIS event pages.")
    return competitions, failures
