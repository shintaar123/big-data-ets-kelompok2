import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
from kafka import KafkaProducer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
TOPIC = os.getenv("GEMPA_API_TOPIC", "gempa-api")
POLL_INTERVAL = int(os.getenv("API_POLL_INTERVAL", "300"))
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

USGS_URL = (
    "https://earthquake.usgs.gov/fdsnws/event/1/query"
    "?format=geojson"
    "&minlatitude=-11&maxlatitude=6"
    "&minlongitude=95&maxlongitude=141"
    "&minmagnitude=2"
    "&orderby=time&limit=20"
)

def create_producer():
    base_config = {
        "bootstrap_servers": KAFKA_BROKER,
        "value_serializer": lambda v: json.dumps(v).encode("utf-8"),
        "key_serializer": lambda k: k.encode("utf-8"),
        "acks": "all",
        "retries": 5,
    }
    try:
        return KafkaProducer(enable_idempotence=True, **base_config)
    except AssertionError:
        print("[WARN] Kafka client tidak mendukung enable_idempotence, memakai konfigurasi kompatibel")
        return KafkaProducer(**base_config)


producer = None
if not DRY_RUN:
    producer = create_producer()

seen_ids = set()


def build_event(feature: dict) -> dict:
    props = feature["properties"]
    coords = feature["geometry"]["coordinates"]
    return {
        "id": feature["id"],
        "magnitude": props.get("mag"),
        "lokasi": props.get("place", "Unknown"),
        "time_utc": datetime.fromtimestamp(
            props["time"] / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "waktu_unix": props["time"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "longitude": coords[0],
        "latitude": coords[1],
        "kedalaman_km": coords[2],
        "alert": props.get("alert"),
        "tsunami": props.get("tsunami", 0),
        "url": props.get("url", ""),
        "sumber": "USGS",
    }


def fetch_and_send():
    try:
        response = requests.get(USGS_URL, timeout=15)
        response.raise_for_status()
        features = response.json().get("features", [])

        sent = 0
        for feature in features:
            eq_id = feature["id"]
            if eq_id in seen_ids:
                continue

            event = build_event(feature)
            if producer is not None:
                producer.send(TOPIC, key=eq_id, value=event)

            seen_ids.add(eq_id)
            sent += 1
            print(f"  [KIRIM] M{event['magnitude']} | {event['lokasi'][:60]}")

        if producer is not None:
            producer.flush()

        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] "
            f"berhasil memproses {sent} gempa baru ke topic '{TOPIC}'"
        )
    except requests.exceptions.Timeout:
        print("[ERROR] Request timeout ke USGS")
    except Exception as exc:
        print(f"[ERROR] {exc}")


if __name__ == "__main__":
    print(f"Producer API dimulai -> topic: {TOPIC}")
    print(f"Polling setiap {POLL_INTERVAL // 60} menit")
    if DRY_RUN:
        print("DRY_RUN aktif: event hanya diambil dan divalidasi, tidak dikirim ke Kafka")
    print("=" * 50)
    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Mengambil data USGS...")
        fetch_and_send()
        print(f"Menunggu {POLL_INTERVAL // 60} menit...")
        time.sleep(POLL_INTERVAL)
