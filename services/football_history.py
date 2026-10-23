"""Local, compact English first-division and Premier League history."""
import json
from functools import lru_cache
from pathlib import Path
from flask import Blueprint, jsonify, render_template

football_history = Blueprint("football_history", __name__)
DATA_PATH = Path(__file__).resolve().parents[1] / "static" / "data"

@lru_cache(maxsize=1)
def compact_top_flight():
    rows = []
    for number in range(1, 5):
        with (DATA_PATH / f"top-flight-{number}.json").open(encoding="utf-8") as handle:
            rows.extend(json.load(handle))
    rows.sort(key=lambda row: (row[1], row[2]))
    years = {row[1] for row in rows}
    if min(years) != 1888 or max(years) != 2024 or len(years) < 120:
        raise ValueError("Unexpected historical season coverage")
    if any(sum(row[1] == year for row in rows) != 20 for year in (2023, 2024)):
        raise ValueError("Incomplete recent Premier League season")
    return rows

@football_history.route("/football-history")
@football_history.route("/football-history/")
def history_page():
    return render_template("football-history.html")

@football_history.route("/api/football-history")
def history_records():
    try:
        rows = compact_top_flight()
    except (OSError, ValueError, TypeError):
        return jsonify({"error": "Local football history dataset is unavailable"}), 503
    return jsonify({"columns": ["club", "year", "position"], "rows": rows,
                    "source": "Fjelstul English Football Database (CC BY-SA 4.0), 1888–2024; 2024–25 Premier League table from premier-league-team-records",
                    "min_year": rows[0][1], "max_year": rows[-1][1]})
