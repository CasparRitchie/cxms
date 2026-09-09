"""Controlled enrichment from official FIS athlete biography pages."""

import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class FisAthleteProfileError(RuntimeError):
    pass


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data):
        if not self.hidden_depth:
            value = re.sub(r"\s+", " ", data).strip()
            if value:
                self.values.append(value)


def parse_fis_athlete_profile(html, source_url=""):
    field_match = re.search(
        r'<li\b(?=[^>]*\bid=["\'](Skis|Snowboard)["\'])[^>]*>(.*?)</li>',
        html, re.I | re.S,
    )
    raw_sponsor = ""
    equipment_type = field_match.group(1).casefold() if field_match else "skis"
    if field_match:
        value_match = re.search(r"profile-info__value[^>]*>(.*?)</span>", field_match.group(2), re.I | re.S)
        if value_match:
            raw_sponsor = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value_match.group(1)))).strip()
    if not field_match:
        parser = _VisibleTextParser()
        parser.feed(html)
        text = " ".join(parser.values)
        match = re.search(r"\b(Skis|Snowboard)\s+(.+?)\s+Boots\b", text, re.I)
        if match:
            equipment_type = match.group(1).casefold()
            raw_sponsor = match.group(2)
    raw_sponsor = raw_sponsor.strip(" -–—")
    ski_sponsor = None if not raw_sponsor or raw_sponsor in {"-", "–", "—"} else raw_sponsor
    if ski_sponsor and (len(ski_sponsor) > 80 or re.search(r"\bFIS Code\b", ski_sponsor, re.I)):
        ski_sponsor = None
    return {
        "ski_sponsor": ski_sponsor,
        "equipment_type": equipment_type,
        "sponsor_source": "fis_official_athlete_profile",
        "sponsor_source_url": source_url,
        "sponsor_checked_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_fis_athlete_profile(url, timeout=20):
    if not re.match(r"^https://www\.fis-ski\.com/DB/general/athlete-biography\.html\?", str(url or ""), re.I):
        raise FisAthleteProfileError("A valid official FIS athlete biography URL is required.")
    request = Request(url, headers={
        "User-Agent": "CXMS Sports Editorial Pilot/1.0",
        "Accept": "text/html",
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            html = response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")
    except HTTPError as exc:
        raise FisAthleteProfileError(f"FIS returned HTTP {exc.code} for the athlete profile.") from exc
    except (URLError, TimeoutError) as exc:
        raise FisAthleteProfileError("The FIS athlete profile is temporarily unavailable.") from exc
    return parse_fis_athlete_profile(html, url)
