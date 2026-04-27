# consumer_to_hdfs.py
# Anggota 3 (bagian 2): baca dari Kafka, simpan ke HDFS dan file lokal

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json
import os
import time
import threading
import subprocess
import requests
from datetime import datetime, timezone
from kafka import KafkaConsumer

# ── KONFIGURASI ───────────────────────────────────────────────
KAFKA_BROKER   = "localhost:9092"
FLUSH_INTERVAL = 120   # flush ke HDFS tiap 2 menit

HDFS_API_PATH  = "/data/gempa/api"
HDFS_RSS_PATH  = "/data/gempa/rss"
LOCAL_API_JSON = "dashboard/data/live_api.json"
LOCAL_RSS_JSON = "dashboard/data/live_rss.json"

# BONUS 1: Telegram Alert — isi token & chat_id kalau mau aktifkan
TELEGRAM_TOKEN   = ""      # contoh: "123456:ABCDef..."
TELEGRAM_CHAT_ID = ""      # contoh: "-100123456"
MIN_MAGNITUDE    = 6.0

# ── HELPER: Telegram Alert ────────────────────────────────────
def send_telegram_alert(event: dict):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    mag   = event.get("magnitude", "?")
    lokasi = event.get("lokasi", "Unknown")
    text  = f"🚨 GEMPA SIGNIFIKAN\nM{mag} di {lokasi}\n{event.get('time_utc','')}"
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10,
        )
        print(f"📩 Telegram alert: M{mag} {lokasi}")
    except Exception as e:
        print(f"[WARN] Telegram: {e}")

# ── HELPER: Simpan ke HDFS via docker exec ────────────────────
def save_to_hdfs(data: list, hdfs_path: str, filename: str):
    tmp_local = f"/tmp/{filename}"
    with open(tmp_local, "w") as f:
        json.dump(data, f, ensure_ascii=False)

    try:
        # copy file ke dalam container namenode
        subprocess.run(
            ["docker", "cp", tmp_local, f"hadoop-namenode:{tmp_local}"],
            check=True, capture_output=True
        )
        # put ke HDFS
        subprocess.run(
            ["docker", "exec", "hadoop-namenode",
             "hdfs", "dfs", "-put", "-f", tmp_local, f"{hdfs_path}/{filename}"],
            check=True, capture_output=True
        )
        print(f"💾 HDFS: {hdfs_path}/{filename} ({len(data)} records)")
    except subprocess.CalledProcessError as e:
        print(f"[WARN] HDFS gagal (pakai lokal saja): {e.stderr.decode()[:80]}")

def save_local(data: list, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── BUFFER (thread-safe) ──────────────────────────────────────
api_buffer = []
rss_buffer = []
api_all    = []
rss_all    = []
lock       = threading.Lock()
batch_num  = 0

# ── FLUSH LOOP ────────────────────────────────────────────────
def flush_loop():
    global batch_num
    while True:
        time.sleep(FLUSH_INTERVAL)
        with lock:
            if api_buffer:
                ts       = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                filename = f"api_{ts}.json"
                save_to_hdfs(list(api_buffer), HDFS_API_PATH, filename)
                api_all.extend(api_buffer)
                save_local(api_all[-500:], LOCAL_API_JSON)
                api_buffer.clear()
                batch_num += 1
                print(f"[Batch #{batch_num}] API flushed ✅")

            if rss_buffer:
                ts       = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                filename = f"rss_{ts}.json"
                save_to_hdfs(list(rss_buffer), HDFS_RSS_PATH, filename)
                rss_all.extend(rss_buffer)
                save_local(rss_all[-200:], LOCAL_RSS_JSON)
                rss_buffer.clear()

# ── CONSUMER ─────────────────────────────────────────────────
def consume():
    consumer = KafkaConsumer(
        "gempa-api", "gempa-rss",
        bootstrap_servers=KAFKA_BROKER,
        group_id="gemparadar-consumer",
        auto_offset_reset="earliest",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        consumer_timeout_ms=1000,
    )

    print("📡 Consumer berjalan — membaca gempa-api & gempa-rss ...")
    while True:
        try:
            for msg in consumer:
                event = msg.value
                with lock:
                    if msg.topic == "gempa-api":
                        api_buffer.append(event)
                        # cek apakah perlu kirim alert
                        mag = float(event.get("magnitude") or 0)
                        if mag >= MIN_MAGNITUDE:
                            send_telegram_alert(event)
                    else:
                        rss_buffer.append(event)
        except Exception as e:
            print(f"[WARN] Consumer error: {e}")
            time.sleep(5)

# ── INISIALISASI HDFS DIRS ────────────────────────────────────
def init_hdfs():
    for path in [HDFS_API_PATH, HDFS_RSS_PATH, "/data/gempa/hasil"]:
        try:
            subprocess.run(
                ["docker", "exec", "hadoop-namenode",
                 "hdfs", "dfs", "-mkdir", "-p", path],
                capture_output=True, timeout=30,
            )
        except Exception:
            pass
    print("📁 HDFS directories siap")

# ── MAIN ─────────────────────────────────────────────────────
if __name__ == "__main__":
    init_hdfs()
    threading.Thread(target=flush_loop, daemon=True).start()
    consume()