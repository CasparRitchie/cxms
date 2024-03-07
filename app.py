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


if __name__ == "__main__":
    # Run the application
    app.run(debug=True)
