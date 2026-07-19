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

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/style-guide")
def style_guide