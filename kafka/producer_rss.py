# producer_rss.py
# Anggota 3 (bagian 1): ambil berita gempa dari RSS BMKG → kirim ke Kafka

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import json
import time
import hashlib
import feedparser
from datetime import datetime, timezone
from kafka import KafkaProducer

# ── KONFIGURASI ───────────────────────────────────────────────
KAFKA_BROKER  = "localhost:9092"
TOPIC         = "gempa-rss"
POLL_INTERVAL = 600   # 10 menit

RSS_FEEDS = [
    "https://www.bmkg.go.id/rss/gempa_m50.xml",
    "https://rss.tempo.co/tag/gempa-bumi",    # backup kalau BMKG down
]

# ── INISIALISASI PRODUCER ─────────────────────────────────────
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    key_serializer=lambda k: k.encode("utf-8"),
    acks="all",
)

seen_urls = set()

def url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]

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

                artikel = {
                    "key":         key,
                    "judul":       entry.get("title", ""),
                    "url":         url,
                    "ringkasan":   entry.get("summary", "")[:300],
                    "tanggal":     entry.get("published", ""),
                    "sumber":      feed.feed.get("title", feed_url),
                    "timestamp":   datetime.now(timezone.utc).isoformat(),
                }

                producer.send(TOPIC, key=key, value=artikel)
                seen_urls.add(key)
                sent += 1
                print(f"  [KIRIM] {artikel['judul'][:60]}")

        except Exception as e:
            print(f"  [WARN] RSS error ({feed_url}): {e}")

    producer.flush()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ {sent} artikel baru dikirim ke '{TOPIC}'")

# ── MAIN LOOP ─────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"📰 Producer RSS dimulai → topic: {TOPIC}")
    print("=" * 50)
    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Mengambil RSS feed...")
        fetch_and_send()
        print(f"   Menunggu {POLL_INTERVAL // 60} menit...")
        time.sleep(POLL_INTERVAL)