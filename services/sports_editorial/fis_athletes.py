import csv
import re
from datetime import datetime, timezone
from io import BytesIO, StringIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile


FIS_POINTS_PAGE = "https://www.fis-ski.com/DB/alpine-skiing/fis-points-lists.html"


class FisAthleteError(RuntimeError):
    pass


def _display_name(firstname, lastname):
    first = re.sub(r"\s+", " ", str(firstname or "").strip()).title()
    last = re.sub(r"\s+", " ", str(lastname or "").strip()).title()
    return " ".join(part for part in (first, last) if part)


def parse_athlete_csv(content, source_url, season_code, list_name=""):
    text = content.decode("utf-8-sig", "replace")
    rows = csv.DictReader(StringIO(text), delimiter="\t")
    imported_at = datetime.now(timezone.utc).isoformat()
    athletes = []
    for row in rows:
        fis_code = str(row.get("Fiscode") or "").strip()
        competitor_id = str(row.get("Competitorid") or "").strip()
        gender = str(row.get("Gender") or "").strip().upper()
        name = _display_name(row.get("Firstname"), row.get("Lastname"))
        # Historic FIS athlete codes can be negative (for example -10220).
        if not re.fullmatch(r"-?\d+", fis_code) or not competitor_id.isdigit() or gender not in ("M", "W") or not name:
            continue
        athletes.append({
            "entity_type": "athlete",
            "name": name,
            "canonical_id": fis_code,
            "canonical_url": f"https://www.fis-ski.com/DB/general/athlete-biography.html?competitorid={competitor_id}&sectorcode=AL",
            "country_code": str(row.get("Nationcode") or "").strip().upper(),
            "metadata": {
                "source": "fis_official_points_list",
                "discipline_code": "AL",
                "season_code": int(season_code),
                "list_name": list_name,
                "competitor_id": competitor_id,
                "gender": gender,
                "birthdate": str(row.get("Birthdate") or "").strip() or None,
                "status": str(row.get("Status") or "").strip() or None,
                "imported_at": imported_at,
                "source_url": source_url,
            },
        })
    return athletes


def _latest_archive_url(page_html, season_code):
    suffix = f"{int(season_code) % 100:02d}"
    pattern = re.compile(rf'https://www\.fis-ski\.com/DB/v2/download/fis-list/ALFP(\d+){suffix}F\.zip', re.I)
    matches = [(int(number), url) for number, url in ((match.group(1), match.group(0)) for match in pattern.finditer(page_html))]
    if not matches:
        raise FisAthleteError(f"No official Alpine CSV archive was found for season {season_code}.")
    return max(matches, key=lambda item: item[0])[1]


def fetch_alpine_athletes(season_code=2027, timeout=30):
    try:
        season = int(season_code)
    except (TypeError, ValueError) as exc:
        raise FisAthleteError("Choose a valid four-digit FIS season.") from exc
    if season < 2000 or season > 2100:
        raise FisAthleteError("Choose a valid four-digit FIS season.")
    page_url = f"{FIS_POINTS_PAGE}?{urlencode({'seasoncode': season, 'sectorcode': 'AL'})}"
    headers = {"User-Agent": "CXMS Sports Editorial Pilot/1.0", "Accept": "text/html,application/zip"}
    try:
        with urlopen(Request(page_url, headers=headers), timeout=timeout) as response:
            page_html = response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")
        archive_url = _latest_archive_url(page_html, season)
        with urlopen(Request(archive_url, headers=headers), timeout=timeout) as response:
            archive = response.read()
    except HTTPError as exc:
        raise FisAthleteError(f"FIS returned HTTP {exc.code} while downloading the athlete list.") from exc
    except (URLError, TimeoutError) as exc:
        raise FisAthleteError("The official FIS points list is temporarily unavailable.") from exc
    try:
        with ZipFile(BytesIO(archive)) as bundle:
            competitor_files = [name for name in bundle.namelist() if name.lower().endswith("com.csv")]
            header_files = [name for name in bundle.namelist() if name.lower().endswith("hdr.csv")]
            if not competitor_files:
                raise FisAthleteError("The FIS archive did not contain its competitor CSV.")
            list_name = ""
            if header_files:
                header_rows = list(csv.DictReader(StringIO(bundle.read(header_files[0]).decode("utf-8-sig", "replace")), delimiter="\t"))
                list_name = (header_rows[0].get("Listname") if header_rows else "") or ""
            athletes = parse_athlete_csv(bundle.read(competitor_files[0]), archive_url, season, list_name)
    except BadZipFile as exc:
        raise FisAthleteError("FIS returned an invalid points-list archive.") from exc
    if not athletes:
        raise FisAthleteError("No individual Alpine athletes were found in the FIS archive.")
    return athletes, archive_url, list_name
