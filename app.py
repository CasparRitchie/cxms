from flask import Flask, render_template, jsonify, send_from_directory, request
import os
import random
from flask import abort, redirect, url_for

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/style-guide")
def style_guide():
    return render_template("style-guide.html")


@app.route("/games")
def games():
    return render_template("games.html")


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
def games_sudoku():
    base = os.path.join(app.root_path, "static", "games", "sudoku")
    return send_from_directory(base, "index.html")


@app.route("/games/sudoblocku")
def games_sudoblocku():
    base = os.path.join(app.root_path, "static", "games", "sudoblocku")
    return send_from_directory(base, "index.html")


<<<<<<< HEAD
from flask import Flask, request, render_template, jsonify

@app.route('/compound-interest', methods=['GET', 'POST'])
=======
@app.route("/compound-interest", methods=["GET", "POST"])
>>>>>>> 3d62d8f (Remove audit route and simplify requirements)
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


@app.route("/myschool")
@app.route("/myschool/")
def myschool_index():
    if not MYSCHOOL_ENABLED:
        return redirect(url_for("index"))
    return app.send_static_file("myschool/index.html")


@app.route("/myschool/<path:filename>")
def myschool_assets(filename):
    if not MYSCHOOL_ENABLED:
        return abort(404)
<<<<<<< HEAD
    return send_from_directory(os.path.join(app.root_path, 'static', 'myschool'), filename)


if __name__ == "__main__":
    # Run the application
=======
    return send_from_directory(os.path.join(app.root_path, "static", "myschool"), filename)


if __name__ == "__main__":
>>>>>>> 3d62d8f (Remove audit route and simplify requirements)
    app.run(debug=True)
