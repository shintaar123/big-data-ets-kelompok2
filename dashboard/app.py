import json
import os
import sys
from datetime import datetime

from flask import Flask, jsonify, render_template

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(__file__)
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
DATA_DIR = os.path.join(BASE_DIR, "data")
PORT = int(os.getenv("PORT", "8000"))


def read_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/results")
def api_results():
    data = read_json("spark_results.json")
    if data is None:
        return jsonify({"error": "Jalankan spark/analysis.py dulu"}), 404
    return jsonify(data)


@app.route("/api/live")
def api_live():
    api_data = read_json("live_api.json") or []
    rss_data = read_json("live_rss.json") or []
    return jsonify(
        {
            "earthquakes": api_data[-20:] if isinstance(api_data, list) else [],
            "news": rss_data[-10:] if isinstance(rss_data, list) else [],
            "updated_at": datetime.now().isoformat(),
        }
    )


@app.route("/api/data")
def api_data():
    spark_data = read_json("spark_results.json") or {}
    live_api = read_json("live_api.json") or []
    live_rss = read_json("live_rss.json") or []
    return jsonify(
        {
            "spark_results": spark_data,
            "live_api": live_api[-20:] if isinstance(live_api, list) else [],
            "live_rss": live_rss[-10:] if isinstance(live_rss, list) else [],
            "updated_at": datetime.now().isoformat(),
        }
    )


@app.route("/api/status")
def api_status():
    files = ["spark_results.json", "live_api.json", "live_rss.json"]
    return jsonify({name: os.path.exists(os.path.join(DATA_DIR, name)) for name in files})


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"GempaRadar Dashboard -> http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=True)
