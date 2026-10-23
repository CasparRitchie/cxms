"""Historical English top-flight league finishing positions.

The upstream multi-megabyte dataset is downloaded only by the Flask server,
then reduced to (club, year, position) once per process. No browser-side
external-data downloads are required.
"""
import json
from functools import lru_cache
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, render_template

football_history = Blueprint("football_history", __name__)
SOURCE = "https://raw.githubusercontent.com/dills122/footy-data-kit/main/data-output/all-seasons.min.json"


@lru_cache(maxsize=1)
def compact_top_flight():
    request = Request(SOURCE, headers={"User-Agent": "cxms-football-history/1.0"})
    with urlopen(request, timeout=25) as response:
        source = json.load(response)
    seasons = source.get("seasons", {})
    records = []
    for year_str, season in seasons.items():
        try:
            year = int(year_str)
        except (TypeError, ValueError):
            continue
        # The original Football League, old Division One and Premier League
        # are all tier1, irrespective of their historical competition names.
        table = season.get("tier1", {}).get("table", [])
        for entry in table:
            club = entry.get("team")
            position = entry.get("pos")
            if club and isinstance(position, int) and position > 0:
                records.append([club, year, position])
    records.sort(key=lambda row: (row[1], row[2]))
    if len(records) < 1500:
        raise ValueError("Upstream historical top-flight data is incomplete")
    return records


@football_history.route("/football-history")
@football_history.route("/football-history/")
def history_page():
    return render_template("football-history.html")


@football_history.route("/api/football-history")
def history_records():
    try:
        rows = compact_top_flight()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return jsonify({"error": "Historical data is temporarily unavailable. Please retry.", "details": type(exc).__name__}), 503
    return jsonify({"columns": ["club", "year", "position"], "rows": rows,
                    "source": "dills122/footy-data-kit", "min_year": min(r[1] for r in rows),
                    "max_year": max(r[1] for r in rows)})
