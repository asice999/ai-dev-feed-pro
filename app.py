from flask import Flask, render_template, jsonify
import json
import os

app = Flask(__name__)
DATA_FILE = "storage/latest.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        return json.load(f)


@app.route("/")
def index():
    data = load_data()
    return render_template("index.html", items=data)


@app.route("/api/feed")
def api():
    return jsonify(load_data())


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
