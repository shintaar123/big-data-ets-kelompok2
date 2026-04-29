import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

import requests
from kafka import KafkaConsumer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
FLUSH_INTERVAL = int(os.getenv("FLUSH_INTERVAL", "120"))
CONSUMER_GROUP_ID = os.getenv("CONSUMER_GROUP_ID", "gemparadar-consumer")

HDFS_API_PATH = "/data/gempa/api"
HDFS_RSS_PATH = "/data/gempa/rss"
HDFS_RESULT_PATH = "/data/gempa/hasil"
LOCAL_API_JSON = "dashboard/data/live_api.json"
LOCAL_RSS_JSON = "dashboard/data/live_rss.json"
LOCAL_MOCK_HDFS_ROOT = os.getenv("LOCAL_MOCK_HDFS_ROOT", "mock_hdfs")
SIMULATE_HDFS = os.getenv("SIMULATE_HDFS", "0") == "1"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
MIN_MAGNITUDE = float(os.getenv("MIN_MAGNITUDE", "6.0"))

api_buffer = []
rss_buffer = []
api_all = []
rss_all = []
lock = threading.Lock()
batch_num = 0


def send_telegram_alert(event: dict):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    text = (
        "GEMPA SIGNIFIKAN\n"
        f"M{event.get('magnitude', '?')} di {event.get('lokasi', 'Unknown')}\n"
        f"{event.get('time_utc', '')}"
    )

    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10,
        )
        print(f"Telegram alert terkirim untuk {event.get('lokasi', 'Unknown')}")
    except Exception as exc:
        print(f"[WARN] Telegram gagal: {exc}")


def save_local(data: list, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def save_to_hdfs(data: list, hdfs_path: str, filename: str) -> bool:
    tmp_dir = os.path.join(os.getcwd(), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_local = os.path.join(tmp_dir, filename)
    container_tmp = f"/tmp/{filename}"

    with open(tmp_local, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    if SIMULATE_HDFS:
        local_target_dir = os.path.join(
            LOCAL_MOCK_HDFS_ROOT,
            hdfs_path.strip("/").replace("/", os.sep),
        )
        os.makedirs(local_target_dir, exist_ok=True)
        local_target = os.path.join(local_target_dir, filename)
        with open(local_target, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        print(f"[SIMULATE_HDFS] {local_target} ({len(data)} records)")
        return True

    try:
        subprocess.run(
            ["docker", "cp", tmp_local, f"hadoop-namenode:{container_tmp}"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "docker",
                "exec",
                "hadoop-namenode",
                "hdfs",
                "dfs",
                "-put",
                "-f",
                container_tmp,
                f"{hdfs_path}/{filename}",
            ],
            check=True,
            capture_output=True,
        )
        print(f"HDFS: {hdfs_path}/{filename} ({len(data)} records)")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"[WARN] Simpan ke HDFS gagal: {exc}")
        return False


def flush_buffer(buffer: list, all_events: list, local_path: str, hdfs_path: str, prefix: str):
    if not buffer:
        return False

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{prefix}_{timestamp}.json"
    payload = list(buffer)

    if not save_to_hdfs(payload, hdfs_path, filename):
        print(f"[WARN] Buffer {prefix} dipertahankan agar tidak kehilangan data")
        return False

    all_events.extend(payload)
    if prefix == "api":
        save_local(all_events[-500:], local_path)
    else:
        save_local(all_events[-200:], local_path)
    buffer.clear()
    return True


def flush_loop():
    global batch_num
    while True:
        time.sleep(FLUSH_INTERVAL)
        with lock:
            if flush_buffer(api_buffer, api_all, LOCAL_API_JSON, HDFS_API_PATH, "api"):
                batch_num += 1
                print(f"[Batch #{batch_num}] API flushed")

            if flush_buffer(rss_buffer, rss_all, LOCAL_RSS_JSON, HDFS_RSS_PATH, "rss"):
                print("[Batch] RSS flushed")


def consume():
    consumer = KafkaConsumer(
        "gempa-api",
        "gempa-rss",
        bootstrap_servers=KAFKA_BROKER,
        group_id=CONSUMER_GROUP_ID,
        auto_offset_reset="earliest",
        value_deserializer=lambda message: json.loads(message.decode("utf-8")),
        consumer_timeout_ms=1000,
    )

    print("Consumer berjalan -> membaca gempa-api dan gempa-rss")
    while True:
        try:
            for message in consumer:
                event = message.value
                with lock:
                    if message.topic == "gempa-api":
                        api_buffer.append(event)
                        magnitude = float(event.get("magnitude") or 0)
                        if magnitude >= MIN_MAGNITUDE:
                            send_telegram_alert(event)
                    else:
                        rss_buffer.append(event)
        except Exception as exc:
            print(f"[WARN] Consumer error: {exc}")
            time.sleep(5)


def init_hdfs():
    if SIMULATE_HDFS:
        for path in [HDFS_API_PATH, HDFS_RSS_PATH, HDFS_RESULT_PATH]:
            local_target_dir = os.path.join(
                LOCAL_MOCK_HDFS_ROOT,
                path.strip("/").replace("/", os.sep),
            )
            os.makedirs(local_target_dir, exist_ok=True)
        print(f"SIMULATE_HDFS aktif -> root lokal: {LOCAL_MOCK_HDFS_ROOT}")
        return

    for path in [HDFS_API_PATH, HDFS_RSS_PATH, HDFS_RESULT_PATH]:
        try:
            subprocess.run(
                ["docker", "exec", "hadoop-namenode", "hdfs", "dfs", "-mkdir", "-p", path],
                capture_output=True,
                check=False,
                timeout=30,
            )
        except Exception:
            pass

    print("Direktori HDFS siap")


if __name__ == "__main__":
    init_hdfs()
    threading.Thread(target=flush_loop, daemon=True).start()
    consume()
