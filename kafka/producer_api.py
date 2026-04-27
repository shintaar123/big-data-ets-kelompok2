# producer_api.py
# Anggota 2: ambil data gempa dari USGS setiap 5 menit → kirim ke Kafka

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json
import time
import requests
from datetime import datetime, timezone
from kafka import KafkaProducer

# ── KONFIGURASI ───────────────────────────────────────────────
KAFKA_BROKER   = "localhost:9092"
TOPIC          = "gempa-api"
POLL_INTERVAL  = 300   # 5 menit

USGS_URL = (
    "https://earthquake.usgs.gov/fdsnws/event/1/query"
    "?format=geojson"
    "&minlatitude=-11&maxlatitude=6"
    "&minlongitude=95&maxlongitude=141"
    "&minmagnitude=2"
    "&orderby=time&limit=20"
)

# ── INISIALISASI PRODUCER ─────────────────────────────────────
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    key_serializer=lambda k: k.encode("utf-8"),
    acks="all",
)

seen_ids = set()  # simpan ID gempa yang sudah dikirim agar tidak duplikat

def fetch_and_send():
    try:
        resp = requests.get(USGS_URL, timeout=15)
        resp.raise_for_status()
        features = resp.json().get("features", [])

        sent = 0
        for feat in features:
            eq_id = feat["id"]
            if eq_id in seen_ids:
                continue   # skip kalau sudah pernah dikirim

            props  = feat["properties"]
            coords = feat["geometry"]["coordinates"]   # [lon, lat, depth]

            event = {
                "id":        eq_id,
                "magnitude": props.get("mag"),
                "lokasi":    props.get("place", "Unknown"),
                "time_utc":  datetime.fromtimestamp(
                                 props["time"] / 1000, tz=timezone.utc
                             ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "waktu_unix": props["time"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "longitude": coords[0],
                "latitude":  coords[1],
                "kedalaman_km": coords[2],
                "alert":     props.get("alert"),
                "tsunami":   props.get("tsunami", 0),
                "url":       props.get("url", ""),
                "sumber":    "USGS",
            }

            producer.send(TOPIC, key=eq_id, value=event)
            seen_ids.add(eq_id)
            sent += 1
            print(f"  [KIRIM] M{event['magnitude']} | {event['lokasi'][:50]}")

        producer.flush()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ {sent} gempa baru dikirim ke '{TOPIC}'")

    except requests.exceptions.Timeout:
        print("[ERROR] Request timeout ke USGS")
    except Exception as e:
        print(f"[ERROR] {e}")

# ── MAIN LOOP ─────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🌋 Producer API dimulai → topic: {TOPIC}")
    print(f"   Polling setiap {POLL_INTERVAL // 60} menit")
    print("=" * 50)
    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Mengambil data USGS...")
        fetch_and_send()
        print(f"   Menunggu {POLL_INTERVAL // 60} menit...")
        time.sleep(POLL_INTERVAL)