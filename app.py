from flask import Flask, request, render_template, jsonify, send_from_directory
import os
import random
from flask import abort, redirect, url_for
import dropbox


def get_dbx():
    """
    Prefer refresh-token auth (recommended: never expires).
    Fall back to access token for local quick testing.
    """
    refresh_token = os.getenv("DROPBOX_REFRESH_TOKEN")
    app_key = os.getenv("DROPBOX_APP_KEY")
    app_secret = os.getenv("DROPBOX_APP_SECRET")

    if refresh_token and app_key and app_secret:
        return dropbox.Dropbox(
            oauth2_refresh_token=refresh_token,
            app_key=app_key,
            app_secret=app_secret,
            timeout=30,
        )

    # Fallback
    token = os.getenv("DROPBOX_ACCESS_TOKEN")
    if token:
        return dropbox.Dropbox(token, timeout=30)

    raise RuntimeError(
        "Dropbox auth missing. Set either "
        "(DROPBOX_REFRESH_TOKEN + DROPBOX_APP_KEY + DROPBOX_APP_SECRET) "
        "or DROPBOX_ACCESS_TOKEN."
    )


app = Flask(__name__)


@app.route('/')
def index():
    # Serve the index.html file
    return render_template('index.html')

@app.route('/audit')
def audit():
    # Serve the index.html file
    return render_template('audit.html')

@app.route('/style-guide')
def style_guide():
    # Serve the style-guide.html file
    return render_template('style-guide.html')


@app.route('/games')
def games():
    # Serve the games.html file
    return render_template('games.html')


@app.route('/games/country-data')
def country_data():
    directory = "static/images/games-images/country-outlines"
    files = os.listdir(directory)
    print("files are ****************")
    # Ensure we have enough files to select from
    if len(files) < 5:
        return jsonify({"error" : "Not enough countries available."}), 500

    selected_files = random.sample(files, 5)  # Randomly pick 5 countries
    # Choose one country to be the correct answer
    correct_country_file = random.choice(selected_files)
    correct_country_name = os.path.splitext(correct_country_file)[0].replace('_', ' ').replace('-', ' ')

    # Prepare data for the game
    game_data = {
        "correct_country": {"name": correct_country_name, "outline": os.path.join("/", directory, correct_country_file)},
        "options": [os.path.splitext(file)[0].replace('_', ' ').replace('-', ' ') for file in selected_files]
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


@app.route('/compound-interest', methods=['GET', 'POST'])
def compound_interest():
    if request.method == 'POST':
        initial_investment = float(request.form.get('initialInvestment', 0))
        monthly_contribution = float(request.form.get('monthlyContribution', 0))
        years = int(request.form.get('years', 0))
        annual_rate = float(request.form.get('annualRate', 0))
        frequency = int(request.form.get('frequency', 1))
        variance_range = float(request.form.get('varianceRange', 0))

        # Map frequency value to actual number of compounding periods per year
        frequency_map = {
            '1': 1,  # Annually
            '2': 2,  # Semi-Annually
            '4': 4,  # Quarterly
            '12': 12,  # Monthly
            '365': 365  # Daily
        }
        comp_periods = frequency_map.get(str(frequency), 1)

        # Calculate compound interest for varied rates
        final_amounts = {}
        rates = [annual_rate + i for i in range(-int(variance_range), int(variance_range) + 1)]
        for rate in rates:
            final_amount = initial_investment
            for _ in range(years * comp_periods):
                final_amount += monthly_contribution / comp_periods
                final_amount *= (1 + (rate / 100) / comp_periods)
            final_amounts[f"Rate {rate}%"] = round(final_amount, 2)

        return jsonify(final_amounts)

    return render_template('compound-interest.html')


EARLY_YEARS_ENABLED = os.getenv("EARLY_YEARS_ENABLED", "0").lower() in ("1", "true", "yes")

@app.route('/early-years')
@app.route('/early-years/')
def early_years_index():
    if not EARLY_YEARS_ENABLED:
        # choose one behaviour:
        # return abort(404)                  # hard 404 (invisible)
        return redirect(url_for('index'))    # soft redirect to home
    base = os.path.join(app.root_path, "static", "early-years")
    return send_from_directory(base, "index.html")

@app.route('/early-years/<path:filename>')
def early_years_assets(filename):
    if not EARLY_YEARS_ENABLED:
        return abort(404)
    base = os.path.join(app.root_path, "static", "early-years")
    return send_from_directory(base, filename)


MYSCHOOL_ENABLED = os.getenv("MYSCHOOL_ENABLED", "1").lower() in ("1", "true", "yes")

@app.route('/myschool')
@app.route('/myschool/')
def myschool_index():
    if not MYSCHOOL_ENABLED:
        return redirect(url_for('index'))
    # Uses Flask's configured static folder (defaults to "<root>/static")
    return app.send_static_file('myschool/index.html')

# You actually don't need this asset route because the HTML references are relative,
# and our handler above is under /myschool/. But if you want to keep it explicit:
@app.route('/myschool/<path:filename>')
def myschool_assets(filename):
    if not MYSCHOOL_ENABLED:
        return abort(404)
    return send_from_directory(os.path.join(app.root_path, 'static', 'myschool'), filename)

# --------------*********************************
# --------------*********************************
# --------------*********************************
# SAMMYS FRIENDS APP
# --------------*********************************
# --------------*********************************
# --------------*********************************

@app.route("/sammysfriends")
@app.route("/sammysfriends/")
def sammysfriends_index():
    base = os.path.join(app.root_path, "static", "sammysfriends")
    return send_from_directory(base, "index.html")


@app.route("/sammysfriends/<path:filename>")
def sammysfriends_assets(filename):
    base = os.path.join(app.root_path, "static", "sammysfriends")
    return send_from_directory(base, filename)


@app.route("/api/sammy/images", methods=["POST"])
def api_sammy_images():
    dbx = get_dbx()
    root = os.getenv("DROPBOX_SAMMY_ROOT", "/sammy-universe/originals_web")

    payload = request.get_json(silent=True) or {}
    limit = int(payload.get("limit", 40))
    cursor = payload.get("cursor")  # raw string, no URL encoding headaches

    if cursor:
        res = dbx.files_list_folder_continue(cursor)
    else:
        res = dbx.files_list_folder(root, limit=limit)

    images = []
    for entry in res.entries:
        if isinstance(entry, dropbox.files.FileMetadata):
            name = entry.name.lower()
            if not name.endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue
            link = dbx.files_get_temporary_link(entry.path_lower).link
            images.append({"id": entry.name, "url": link})

    images.sort(key=lambda x: x["id"].lower())

    return jsonify({
        "count": len(images),
        "images": images,
        "has_more": res.has_more,
        "cursor": res.cursor if res.has_more else None
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
