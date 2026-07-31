from flask import Flask, render_template, jsonify, send_from_directory, request
import os
import random
import json
from flask import abort, redirect, url_for

from services.data_explorer.eda_engine import (
    build_eda_report,
    get_sample_dataset_csv,
    parse_csv_dataset,
)
from services.sports_editorial import sports_editorial_workspace
from services.level_crossing.td_feed import td_feed

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "sports-editorial-pilot-dev-only")
app.register_blueprint(sports_editorial_workspace)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/style-guide")
def style_guide():
    return render_template("style-guide.html")


@app.route("/games")
def games():
    return render_template("games.html")


@app.route("/circuit-training")
@app.route("/circuit-training/")
def circuit_training():
    return render_template("circuit-training.html")


@app.route("/level-crossing")
@app.route("/level-crossing/")
def level_crossing():
    td_feed.start()
    return render_template("level-crossing.html")


@app.route("/api/level-crossing/td-status")
def level_crossing_td_status():
    td_feed.start()
    return jsonify(td_feed.snapshot())


@app.route("/gcse/history")
@app.route("/gcse/history/")
def gcse_history():
    return render_template("gcse-history.html")


@app.route("/football")
@app.route("/football/")
def football():
    return render_template("football.html")


@app.route("/sports-editorial")
@app.route("/sports-editorial/")
def sports_editorial():
    return render_template("sports-editorial.html")


@app.route("/games/country-data")
def country_data():
    directory = "static/images/games-images/country-outlines"
    files = os.listdir(directory)

    if len(files) < 5:
        return jsonify({"error": "Not enough countries available."}), 500

    selected_files = random.sample(files, 5)
    correct_country_file = random.choice(selected_files)
    correct_country_name = (
        os.path.splitext(correct_country_file)[0]
        .replace("_", " ")
        .replace("-", " ")
    )

    game_data = {
        "correct_country": {
            "name": correct_country_name,
            "outline": os.path.join("/", directory, correct_country_file),
        },
        "options": [
            os.path.splitext(file)[0].replace("_", " ").replace("-", " ")
            for file in selected_files
        ],
    }
    return jsonify(game_data)


@app.route("/games/sudoku")
@app.route("/games/sudoku/")
def games_sudoku():
    base = os.path.join(app.root_path, "static", "games", "sudoku")
    return send_from_directory(base, "index.html")


@app.route("/games/sudoku/<path:filename>")
def games_sudoku_assets(filename):
    base = os.path.join(app.root_path, "static", "games", "sudoku")
    return send_from_directory(base, filename)


@app.route("/games/sudoblocku")
@app.route("/games/sudoblocku/")
def games_sudoblocku():
    base = os.path.join(app.root_path, "static", "games", "sudoblocku")
    return send_from_directory(base, "index.html")


@app.route("/games/sudoblocku/<path:filename>")
def games_sudoblocku_assets(filename):
    base = os.path.join(app.root_path, "static", "games", "sudoblocku")
    return send_from_directory(base, filename)


@app.route("/compound-interest", methods=["GET", "POST"])
def compound_interest():
    if request.method == "POST":
        initial_investment = float(request.form.get("initialInvestment", 0))
        monthly_contribution = float(request.form.get("monthlyContribution", 0))
        years = int(request.form.get("years", 0))
        annual_rate = float(request.form.get("annualRate", 0))
        frequency = int(request.form.get("frequency", 1))
        variance_range = float(request.form.get("varianceRange", 0))

        frequency_map = {
            "1": 1,
            "2": 2,
            "4": 4,
            "12": 12,
            "365": 365,
        }
        comp_periods = frequency_map.get(str(frequency), 1)

        final_amounts = {}
        rates = [
            annual_rate + i
            for i in range(-int(variance_range), int(variance_range) + 1)
        ]

        for rate in rates:
            final_amount = initial_investment
            for _ in range(years * comp_periods):
                final_amount += monthly_contribution / comp_periods
                final_amount *= (1 + (rate / 100) / comp_periods)
            final_amounts[f"Rate {rate}%"] = round(final_amount, 2)

        return jsonify(final_amounts)

    return render_template("compound-interest.html")


EARLY_YEARS_ENABLED = os.getenv("EARLY_YEARS_ENABLED", "0").lower() in ("1", "true", "yes")


@app.route("/early-years")
@app.route("/early-years/")
def early_years_index():
    if not EARLY_YEARS_ENABLED:
        return redirect(url_for("index"))
    base = os.path.join(app.root_path, "static", "early-years")
    return send_from_directory(base, "index.html")


@app.route("/early-years/<path:filename>")
def early_years_assets(filename):
    if not EARLY_YEARS_ENABLED:
        return abort(404)
    base = os.path.join(app.root_path, "static", "early-years")
    return send_from_directory(base, filename)


MYSCHOOL_ENABLED = os.getenv("MYSCHOOL_ENABLED", "1").lower() in ("1", "true", "yes")


@app.route("/myschool-app/")
def myschool_app():
    if not MYSCHOOL_ENABLED:
        return redirect(url_for("index"))
    return app.send_static_file("myschool/index.html")


@app.route("/myschool-app/<path:filename>")
def myschool_app_assets(filename):
    if not MYSCHOOL_ENABLED:
        return abort(404)
    return send_from_directory(os.path.join(app.root_path, "static", "myschool"), filename)


@app.route("/myschool")
@app.route("/myschool/")
def myschool_page():
    if not MYSCHOOL_ENABLED:
        return redirect(url_for("index"))
    return render_template("myschool.html")


@app.route("/data-explorer")
def data_explorer():
    return render_template("data-explorer.html")


@app.route("/api/data-explorer/analyse", methods=["POST"])
def analyse_dataset():
    payload = request.get_json(silent=True) or {}
    raw_data = payload.get("dataset", "")

    if not raw_data.strip():
        return jsonify({"ok": False, "error": "No dataset provided."}), 400

    try:
        df = parse_csv_dataset(raw_data)
        analysis = build_eda_report(df)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": f"Unexpected analysis error: {str(exc)}"
        }), 500

    return jsonify({
        "ok": True,
        "analysis": analysis
    })


@app.route("/api/data-explorer/sample/<dataset_name>")
def sample_dataset(dataset_name):
    try:
        csv_data = get_sample_dataset_csv(dataset_name)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404

    return jsonify({
        "ok": True,
        "dataset_name": dataset_name,
        "csv": csv_data,
    })


@app.route("/api/football/worldcup/fixtures")
def worldcup_fixtures():
    fixtures_path = os.path.join(app.root_path, "static/data", "worldcup_2026_fixtures.json")

    with open(fixtures_path, "r", encoding="utf-8") as file:
        fixtures = json.load(file)

    return jsonify({
        "ok": True,
        "fixtures": fixtures
    })


if __name__ == "__main__":
    # Run the application

    app.run(debug=True)
