import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

import feedparser
from kafka import KafkaProducer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
TOPIC = os.getenv("GEMPA_RSS_TOPIC", "gempa-rss")
POLL_INTERVAL = int(os.getenv("RSS_POLL_INTERVAL", "300"))
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

RSS_FEEDS = [
    "https://www.bmkg.go.id/rss/gempa_m50.xml",
    "https://rss.tempo.co/tag/gempa-bumi",
]

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

seen_urls = set()


def url_hash(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:8]


def fetch_and_send():
    sent = 0
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                key = url_hash(url)
                if key in seen_urls:
                    continue

                article = {
                    "key": key,
                    "judul": entry.get("title", ""),
                    "url": url,
                    "ringkasan": entry.get("summary", "")[:300],
                    "tanggal": entry.get("published", ""),
                    "sumber": feed.feed.get("title", feed_url),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                if producer is not None:
                    producer.send(TOPIC, key=key, value=article)

                seen_urls.add(key)
                sent += 1
                print(f"  [KIRIM] {article['judul'][:70]}")
        except Exception as exc:
            print(f"[WARN] RSS error ({feed_url}): {exc}")

    if producer is not None:
        producer.flush()

    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] "
        f"berhasil memproses {sent} artikel baru ke topic '{TOPIC}'"
    )


if __name__ == "__main__":
    print(f"Producer RSS dimulai -> topic: {TOPIC}")
    if DRY_RUN:
        print("DRY_RUN aktif: artikel hanya diambil dan divalidasi, tidak dikirim ke Kafka")
    print("=" * 50)
    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Mengambil RSS feed...")
        fetch_and_send()
        print(f"Menunggu {POLL_INTERVAL // 60} menit...")
        time.sleep(POLL_INTERVAL)
