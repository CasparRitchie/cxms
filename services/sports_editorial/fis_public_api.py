import csv
import os
import re
from datetime import datetime, timezone
from io import BytesIO, StringIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile
from time import monotonic


FIS_PUBLIC_API_URL = "https://api.fis-ski.com"
SUPPORTED_DISCIPLINES = {
    "AL": ("alpine_skiing",),
    "JP": ("ski_jumping",),
    "CC": ("cross_country_skiing",),
    "NK": ("nordic_combined",),
    "FS": ("freestyle", "freeski_park_and_pipe", "freestyle_ski_cross"),
    "SB": ("snowboard_cross", "snowboard_park_and_pipe", "snowboard_alpine"),
}
SUPPORTED_CATEGORIES = {"WC", "WSC"}
_calendar_cache = {}


class FisPublicApiError(RuntimeError):
    pass


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _date(value):
    return _clean(value).split(" ", 1)[0] or None


def _is_cancelled_comment(value):
    text = _clean(value).casefold()
    if not re.search(r"\bcancel(?:l)?ed\b", text):
        return False
    return not re.search(r"\b(?:not|never)\s+(?:been\s+)?cancel(?:l)?ed\b", text)


def _rows(content):
    return csv.DictReader(StringIO(content.decode("utf-8-sig", "replace").replace("\x00", "")), delimiter="\t")


def _download_feed(name, timeout=30):
    api_key = os.getenv("FIS_PUBLIC_API_KEY", "").strip()
    if not api_key:
        raise FisPublicApiError("FIS_PUBLIC_API_KEY is not configured.")
    url = f"{os.getenv('FIS_PUBLIC_API_BASE_URL', FIS_PUBLIC_API_URL).rstrip('/')}/data-feeds/{name}"
    request = Request(url, headers={
        "X-Api-Key": api_key,
        "Accept": "application/zip",
        "User-Agent": "CXMS Sports Editorial/1.0",
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            archive = response.read()
    except HTTPError as exc:
        if exc.code == 401:
            message = "FIS rejected the Public API key. Generate or replace FIS_PUBLIC_API_KEY in the FIS Member Section."
        elif exc.code == 429:
            message = "The FIS Public API rate limit has been reached. Wait a minute before refreshing again."
        else:
            message = f"FIS returned HTTP {exc.code} while downloading the {name} feed."
        raise FisPublicApiError(message) from exc
    except (URLError, TimeoutError) as exc:
        raise FisPublicApiError(f"The FIS {name} feed is temporarily unavailable.") from exc
    try:
        return ZipFile(BytesIO(archive)), url
    except BadZipFile as exc:
        raise FisPublicApiError(f"FIS returned an invalid {name} feed archive.") from exc


def parse_competitor_feed(files, source_url):
    imported_at = datetime.now(timezone.utc).isoformat()
    athletes = []
    for discipline_code in SUPPORTED_DISCIPLINES:
        filename = f"A_compet{discipline_code.lower()}.csv"
        if filename not in files:
            continue
        for row in _rows(files[filename]):
            fis_code = _clean(row.get("Fiscode"))
            competitor_id = _clean(row.get("Competitorid"))
            first_name = _clean(row.get("Firstname")).title()
            last_name = _clean(row.get("Lastname")).title()
            gender = _clean(row.get("Gender")).upper()
            if (_clean(row.get("Type")).lower() != "athlete" or
                    not re.fullmatch(r"-?\d+", fis_code) or not competitor_id.isdigit() or
                    gender not in ("M", "W") or not (first_name or last_name)):
                continue
            status_code = _clean(row.get("Status")).upper()
            athletes.append({
                "entity_type": "athlete",
                "name": " ".join(part for part in (first_name, last_name) if part),
                "canonical_id": fis_code,
                "canonical_url": ("https://www.fis-ski.com/DB/general/athlete-biography.html"
                                  f"?competitorid={competitor_id}&sectorcode={discipline_code}"),
                "country_code": _clean(row.get("Nationcode")).upper(),
                "metadata": {
                    "source": "fis_public_api_competitors_feed",
                    "discipline_code": discipline_code,
                    "competitor_id": competitor_id,
                    "gender": gender,
                    "birth_year": int(row["Birthyear"]) if _clean(row.get("Birthyear")).isdigit() else None,
                    "ski_club": _clean(row.get("Skiclub")) or None,
                    "status": status_code or None,
                    "is_active": status_code == "O",
                    "imported_at": imported_at,
                    "source_url": source_url,
                },
            })
    if not athletes:
        raise FisPublicApiError("No supported athletes were found in the FIS competitors feed.")
    return athletes


def fetch_public_athletes(timeout=30):
    bundle, source_url = _download_feed("competitors", timeout)
    try:
        files = {name: bundle.read(name) for name in bundle.namelist()}
    finally:
        bundle.close()
    athletes = parse_competitor_feed(files, source_url)
    return athletes, source_url, "FIS Public API competitors feed"


def _sport_values(discipline_code, race_codes):
    if discipline_code == "FS":
        values = []
        if race_codes & {"MO", "DM", "AE", "AET", "DMT"}: values.append("freestyle")
        if race_codes & {"SS", "HP", "BA", "ST"}: values.append("freeski_park_and_pipe")
        if race_codes & {"SX", "SXT"}: values.append("freestyle_ski_cross")
        return values or list(SUPPORTED_DISCIPLINES[discipline_code])
    if discipline_code == "SB":
        values = []
        if race_codes & {"SBX", "SX", "SXT"}: values.append("snowboard_cross")
        if race_codes & {"SS", "HP", "BA", "ST"}: values.append("snowboard_park_and_pipe")
        if race_codes & {"PGS", "PSL", "GS", "PRT"}: values.append("snowboard_alpine")
        return values or list(SUPPORTED_DISCIPLINES[discipline_code])
    return list(SUPPORTED_DISCIPLINES[discipline_code])


def parse_calendar_feed(files, source_url, season_code):
    season = int(season_code)
    imported_at = datetime.now(timezone.utc).isoformat()
    event_rows = {str(row.get("Eventid")): row for row in _rows(files.get("A_event.csv", b""))}
    races_by_event = {}
    competitions = []
    for discipline_code in SUPPORTED_DISCIPLINES:
        filename = f"A_race{discipline_code.lower()}.csv"
        if filename not in files:
            continue
        for row in _rows(files[filename]):
            if _clean(row.get("Seasoncode")) != str(season):
                continue
            categories = [_clean(row.get(name)).upper() for name in ("Catcode", "Catcode2", "Catcode3", "Catcode4")]
            if not SUPPORTED_CATEGORIES.intersection(categories):
                continue
            race_id, event_id = _clean(row.get("Raceid")), _clean(row.get("Eventid"))
            if not race_id.isdigit() or not event_id.isdigit():
                continue
            event_row = event_rows.get(event_id, {})
            place = _clean(row.get("Place")) or _clean(event_row.get("Place"))
            nation = _clean(row.get("Nationcode")) or _clean(event_row.get("Nationcodeplace"))
            description = _clean(row.get("DESCRIPTION")) or "Race"
            gender = _clean(row.get("Gender")).upper()
            codex = _clean(row.get("Racecodex"))
            race_code = _clean(row.get("Disciplinecode")).upper()
            category = next((value for value in categories if value in SUPPORTED_CATEGORIES), categories[0] or "")
            date = _date(row.get("Racedate"))
            webcomment = _clean(row.get("Webcomment"))
            cancelled = _is_cancelled_comment(webcomment)
            team = _clean(row.get("Team")) == "1"
            training = "training" in description.casefold()
            qualification = categories[0] == "QUA" or "qualification" in description.casefold()
            competition_kind = ("training" if training else "qualification" if qualification
                                else "team_event" if team else "race")
            competitions.append({
                "entity_type": "competition",
                "name": " · ".join(part for part in (description, gender, place, date, f"codex {codex}" if codex else "") if part),
                "canonical_id": race_id,
                "canonical_url": f"https://www.fis-ski.com/DB/general/results.html?sectorcode={discipline_code}&raceid={race_id}",
                "country_code": nation.upper(),
                "metadata": {
                    "source": "fis_public_api_calendar_feed", "discipline_code": discipline_code,
                    "event_id": event_id, "season_code": season, "category_code": category,
                    "codex": codex, "event_code": race_code, "gender": gender, "date": date,
                    "location": place, "competition_kind": competition_kind,
                    "race_status": "cancelled" if cancelled else "scheduled",
                    "official_status_comment": webcomment or None,
                    "is_result_expected": not training and not qualification and not team and not cancelled,
                    "imported_at": imported_at, "source_url": source_url,
                },
            })
            races_by_event.setdefault(event_id, {"discipline": discipline_code, "codes": set(), "categories": set()})
            races_by_event[event_id]["codes"].add(race_code)
            races_by_event[event_id]["categories"].add(category)
    events = []
    for event_id, summary in races_by_event.items():
        row = event_rows.get(event_id, {})
        place = _clean(row.get("Place"))
        nation = _clean(row.get("Nationcodeplace"))
        name = _clean(row.get("Eventname")) or place or f"FIS event {event_id}"
        discipline_code = summary["discipline"]
        events.append({
            "entity_type": "event", "name": name, "canonical_id": event_id,
            "canonical_url": ("https://www.fis-ski.com/DB/general/event-details.html"
                              f"?sectorcode={discipline_code}&eventid={event_id}&seasoncode={season}"),
            "country_code": nation.upper(),
            "metadata": {
                "source": "fis_public_api_calendar_feed", "discipline_code": discipline_code,
                "category_code": sorted(summary["categories"])[0],
                "sport_values": _sport_values(discipline_code, summary["codes"]),
                "location_label": place or name, "start_date": _date(row.get("Startdate")),
                "end_date": _date(row.get("Enddate")), "season_code": season,
                "imported_at": imported_at, "source_url": source_url,
            },
        })
    if not events or not competitions:
        raise FisPublicApiError(f"No supported FIS calendar data was found for season {season}.")
    return events, competitions


def fetch_public_calendar_feed(season_code=2027, timeout=30):
    try:
        season = int(season_code)
    except (TypeError, ValueError) as exc:
        raise FisPublicApiError("Choose a valid four-digit FIS season.") from exc
    if season < 1967 or season > 2100:
        raise FisPublicApiError("Choose a FIS season from 1967 onwards.")
    cached = _calendar_cache.get(season)
    if cached and monotonic() - cached[0] < 60:
        return cached[1]
    bundle, source_url = _download_feed("calendar", timeout)
    try:
        files = {name: bundle.read(name) for name in bundle.namelist()}
    finally:
        bundle.close()
    events, competitions = parse_calendar_feed(files, source_url, season)
    result = (events, competitions, source_url)
    _calendar_cache[season] = (monotonic(), result)
    return result
