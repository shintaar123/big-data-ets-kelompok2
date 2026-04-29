import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import feedparser
from dateutil import parser as date_parser
from kafka import KafkaProducer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
TOPIC = os.getenv("GEMPA_RSS_TOPIC", "gempa-rss")
POLL_INTERVAL = int(os.getenv("RSS_POLL_INTERVAL", "300"))
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"
BACKFILL_DAYS = int(os.getenv("RSS_BACKFILL_DAYS", "7"))
CACHE_FILE = ".rss_cache.json"

RSS_FEEDS = [
    # Feed 1: Breaking news (Antara)
    "https://www.antaranews.com/rss/terkini",
    # Feed 2: National news (CNN)
    "https://www.cnnindonesia.com/nasional/rss",
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


def load_cache() -> set:
    """Load seen URL hashes dari file cache"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                print(f"[CACHE] Loaded {len(cached)} cached URLs")
                return set(cached)
        except Exception as exc:
            print(f"[WARN] Gagal load cache: {exc}")
    return set()


def save_cache(seen_urls: set) -> None:
    """Simpan seen URL hashes ke file cache"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen_urls), f)
    except Exception as exc:
        print(f"[WARN] Gagal save cache: {exc}")


seen_urls = load_cache()


def url_hash(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:8]


def fetch_and_send():
    sent = 0
    skipped_cache = 0
    skipped_old = 0
    errors = 0
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            feed_title = feed.feed.get("title", feed_url)
            articles_count = len(feed.entries)
            print(f"\n  📰 Feed: {feed_title}")
            print(f"     Artikel dalam feed: {articles_count}")

            for entry in feed.entries:
                url = entry.get("link", "")
                key = url_hash(url)

                # Check cache (deduplication)
                if key in seen_urls:
                    skipped_cache += 1
                    continue

                # Check backfill date
                published_str = entry.get("published", "")
                if published_str:
                    try:
                        published_date = date_parser.parse(published_str)
                        if published_date.tzinfo is None:
                            published_date = published_date.replace(tzinfo=timezone.utc)
                        if published_date < cutoff_date:
                            skipped_old += 1
                            continue
                    except Exception:
                        pass

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
                print(f"     ✓ {article['judul'][:70]}")

        except Exception as exc:
            errors += 1
            print(f"  [ERROR] {feed_url}: {exc}")

    if producer is not None:
        producer.flush()

    # Save cache after processing
    save_cache(seen_urls)

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] SUMMARY:")
    print(f"  Sent:          {sent} artikel baru")
    print(f"  Skipped cache: {skipped_cache} artikel (sudah dikirim sebelumnya)")
    print(f"  Skipped old:   {skipped_old} artikel (lebih lama dari {BACKFILL_DAYS} hari)")
    print(f"  Errors:        {errors}")
    print(f"  Total cache:   {len(seen_urls)} URL")


if __name__ == "__main__":
    print(f"Producer RSS dimulai -> topic: {TOPIC}")
    print(f"Backfill: {BACKFILL_DAYS} hari terakhir")
    print(f"Polling interval: {POLL_INTERVAL} detik ({POLL_INTERVAL // 60} menit)")
    if DRY_RUN:
        print("DRY_RUN aktif: artikel hanya diambil dan divalidasi, tidak dikirim ke Kafka")
    print("=" * 60)
    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Mengambil RSS feed...")
        fetch_and_send()
        print(f"Menunggu {POLL_INTERVAL // 60} menit sebelum polling berikutnya...")
        time.sleep(POLL_INTERVAL)
