import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json
import os
from flask import Flask, jsonify, render_template
from datetime import datetime

app = Flask(__name__)
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def read_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/results")
def api_results():
    data = read_json("spark_results.json")
    if data is None:
        return jsonify({"error": "Jalankan spark/analysis.py dulu!"}), 404
    return jsonify(data)

@app.route("/api/live")
def api_live():
    api_data = read_json("live_api.json") or []
    rss_data = read_json("live_rss.json") or []
    return jsonify({
        "earthquakes": api_data[-20:] if isinstance(api_data, list) else [],
        "news":        rss_data[-10:] if isinstance(rss_data, list) else [],
        "updated_at":  datetime.now().isoformat(),
    })

@app.route("/api/status")
def api_status():
    files = ["spark_results.json", "live_api.json", "live_rss.json"]
    return jsonify({f: os.path.exists(os.path.join(DATA_DIR, f)) for f in files})

if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    print("🌋 GempaRadar Dashboard → http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)