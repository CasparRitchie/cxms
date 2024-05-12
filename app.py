from flask import Flask, render_template, jsonify
import os
import random


app = Flask(__name__)


@app.route('/')
def index():
    # Serve the index.html file
    return render_template('index.html')

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


from flask import Flask, request, render_template, jsonify

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




if __name__ == "__main__":
    # Run the application
    app.run(debug=True)
