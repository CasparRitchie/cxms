"""Normalisation and shared comparison context for Alpine result detectors."""

from collections import defaultdict
from datetime import date, datetime
import re


NON_START_STATUSES = {"did_not_start", "dns", "not_started"}
NON_FINISH_STATUSES = {"did_not_finish", "dnf", "did_not_qualify", "dnq", "disqualified", "dsq"}


def parse_date(value):
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def seconds(value):
    """Parse a FIS total or difference time without deciding which one it is."""
    text = str(value or "").strip().replace("’", "'").replace("\"", "")
    if not text or text.casefold() in {"none", "nan", "-", "—"}:
        return None
    text = text.lstrip("+")
    try:
        if ":" in text:
            parts = text.split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return float(text)
    except (TypeError, ValueError):
        return None


def normalise_country(code, mapping=None):
    """Preserve historical entities unless a caller supplies an explicit mapping."""
    cleaned = re.sub(r"[^A-Z0-9]", "", str(code or "").upper())
    return (mapping or {}).get(cleaned, cleaned)


def athlete_key(row):
    if str(row.get("fis_code") or "").strip():
        return f"fis:{str(row['fis_code']).strip()}"
    if str(row.get("competitor_id") or "").strip():
        return f"competitor:{str(row['competitor_id']).strip()}"
    # Legacy/demo fallback deliberately includes nationality; name alone is never
    # treated as a stable identity and confidence is reduced by the engine.
    return f"legacy:{str(row.get('athlete') or '').casefold()}|{str(row.get('nation') or '').upper()}"


def race_key(row):
    race_id = str(row.get("race_id") or "").strip()
    if race_id:
        return f"race:{race_id}"
    return "fallback:" + "|".join(str(row.get(field) or "").casefold() for field in (
        "date", "venue", "course", "discipline", "gender", "competition",
    ))


def evidence_row(row, **calculated):
    evidence = {
        "race_id": str(row.get("race_id") or ""), "race_date": row.get("date") or "",
        "venue": row.get("venue") or "", "course": row.get("course") or "",
        "discipline": row.get("discipline") or "", "gender": row.get("gender") or "",
        "athlete_id": athlete_key(row), "fis_code": str(row.get("fis_code") or ""),
        "athlete_name": row.get("athlete") or "", "nation": row.get("nation") or "",
        "placing": row.get("place"), "status": row.get("status") or "",
        "total_time": row.get("total_time") or row.get("time") or "",
        "difference_time": row.get("diff_time") or "",
    }
    evidence.update(calculated)
    return evidence


def exact_age(birth_date, race_date):
    born, raced = parse_date(birth_date), parse_date(race_date)
    if not born or not raced or born > raced:
        return None
    total_days = (raced - born).days
    years = raced.year - born.year - ((raced.month, raced.day) < (born.month, born.day))
    try:
        anniversary = born.replace(year=born.year + years)
    except ValueError:  # 29 February in a non-leap anniversary year.
        anniversary = born.replace(year=born.year + years, day=28)
    remaining_days = (raced - anniversary).days
    return {"days": total_days, "years": years, "remaining_days": remaining_days,
            "display": f"{years} years, {remaining_days} days", "exact": True}


def age_at(row):
    exact = exact_age(row.get("birth_date"), row.get("date"))
    if exact:
        return exact
    year = str(row.get("birth_year") or "")
    race = parse_date(row.get("date"))
    if year.isdigit() and race:
        years = race.year - int(year)
        return {"days": None, "years": years, "display": f"approximately {years}", "exact": False}
    return None


def winning_margin(race_rows):
    """Return a compatible first-to-second margin, or None for ties/bad data."""
    winners = [row for row in race_rows if row.get("place") == 1]
    seconds_rows = [row for row in race_rows if row.get("place") == 2]
    if len(winners) != 1 or not seconds_rows:
        return None
    winner, runner_up = winners[0], seconds_rows[0]
    diff = seconds(runner_up.get("diff_time"))
    if diff is None and str(runner_up.get("time") or "").strip().startswith("+"):
        diff = seconds(runner_up.get("time"))
    if diff is None:
        winner_total = seconds(winner.get("total_time") or winner.get("time"))
        runner_total = seconds(runner_up.get("total_time") or runner_up.get("time"))
        if winner_total is not None and runner_total is not None and runner_total >= winner_total:
            diff = runner_total - winner_total
    if diff is None or diff < 0:
        return None
    return {"seconds": round(diff, 3), "winner": winner, "runner_up": runner_up}


class InsightContext:
    def __init__(self, rows, coverage=None, country_mapping=None):
        self.country_mapping = country_mapping or {}
        normalised, seen = [], set()
        for source in rows:
            row = dict(source)
            row["status"] = str(row.get("status") or "finished").casefold().replace(" ", "_")
            row["nation_original"] = str(row.get("nation") or "").upper()
            row["nation"] = normalise_country(row.get("nation"), self.country_mapping)
            row["athlete_id"] = athlete_key(row)
            row["race_key"] = race_key(row)
            row["parsed_date"] = parse_date(row.get("date"))
            dedupe_key = (row["race_key"], row["athlete_id"])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalised.append(row)
        self.rows = sorted(normalised, key=lambda r: (r.get("parsed_date") or date.min, r["race_key"], r.get("place") or 999))
        self.by_athlete = defaultdict(list)
        self.by_race = defaultdict(list)
        for row in self.rows:
            self.by_athlete[row["athlete_id"]].append(row)
            self.by_race[row["race_key"]].append(row)
        dates = [row["date"] for row in self.rows if row.get("parsed_date")]
        supplied = dict(coverage or {})
        self.coverage = {
            "coverage_type": supplied.get("coverage_type", "loaded_results_only"),
            "earliest_race_date": min(dates) if dates else None,
            "latest_race_date": max(dates) if dates else None,
            "race_count": len(self.by_race),
            "is_known_complete": bool(supplied.get("is_known_complete", False)),
            "warnings": list(supplied.get("warnings") or []),
        }
        if any(not str(row.get("race_id") or "") for row in self.rows):
            self.coverage["warnings"].append("Some races use date, venue, discipline, gender and competition as a fallback identity.")
        if any(row["athlete_id"].startswith("legacy:") for row in self.rows):
            self.coverage["warnings"].append("Some athletes lack a stable FIS identifier and use a name-and-nation fallback.")
        self.data_as_of = self.coverage["latest_race_date"]

    def scope(self, rows=None, **overrides):
        rows = rows or self.rows
        values = lambda field: sorted({row.get(field) for row in rows if row.get(field)})
        scope = {
            "competition": values("competition"), "gender": values("gender"),
            "disciplines": values("discipline"), "season": values("season_code"),
            "venue": values("venue")[0] if len(values("venue")) == 1 else None,
            "comparison_scope": "complete history" if self.coverage["is_known_complete"] else "loaded results",
        }
        scope.update(overrides)
        return scope

    def coverage_warning(self):
        if self.coverage["is_known_complete"]:
            return None
        return "Limited to the currently loaded classifications; this is not an all-time claim."

    @staticmethod
    def is_start(row):
        return row.get("status") not in NON_START_STATUSES

    @staticmethod
    def is_finish(row):
        return isinstance(row.get("place"), int) and row.get("status") not in NON_FINISH_STATUSES
