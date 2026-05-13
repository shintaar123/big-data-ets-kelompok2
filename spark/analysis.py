"""
GempaRadar — Spark Continuous Analysis
=======================================
Menjalankan analisis gempa secara terus-menerus setiap SPARK_INTERVAL detik.
Spark session TIDAK pernah di-stop; hanya data yang di-reload setiap siklus.

Strategi sumber data (urutan prioritas):
  1. HDFS via docker bridge  (docker exec hadoop-namenode hdfs dfs -cat …)
  2. File lokal dashboard/data/live_api.json  (jika docker tidak tersedia)

Spark TIDAK mencoba connect HDFS secara langsung agar tidak tersangkut
di DataNode 172.18.0.x yang tidak bisa diakses dari Windows host.

ML (RandomForest) hanya dijalankan setiap ML_EVERY_N_CYCLES siklus karena
proses training relatif lambat. Hasil ML terakhir dipakai di siklus antara.
"""

import sys

try:
    import distutils  # noqa: F401
except ImportError:
    import setuptools
    sys.modules["distutils"] = setuptools._distutils

import json
import os
import subprocess
import time
from datetime import datetime

# ─── Path / env setup ────────────────────────────────────────────────────────
PROJECT_ROOT    = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAFE_TEMP_DIR   = os.path.join(PROJECT_ROOT, ".spark_tmp")
os.makedirs(SAFE_TEMP_DIR, exist_ok=True)
os.environ["TEMP"]             = SAFE_TEMP_DIR
os.environ["TMP"]              = SAFE_TEMP_DIR
os.environ["SPARK_LOCAL_DIRS"] = os.path.join(SAFE_TEMP_DIR, "local")
os.makedirs(os.environ["SPARK_LOCAL_DIRS"], exist_ok=True)
os.environ.setdefault("PYSPARK_PYTHON",        sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

from pyspark.sql import SparkSession          # noqa: E402
from pyspark.sql import functions as F        # noqa: E402
from pyspark.sql.functions import (           # noqa: E402
    date_format, hour as spark_hour, to_timestamp, when,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ─── Config ──────────────────────────────────────────────────────────────────
STAGING_DIR   = os.path.join(PROJECT_ROOT, "tmp", "spark_bridge")
os.makedirs(STAGING_DIR, exist_ok=True)

LOCAL_PATH     = os.path.join(PROJECT_ROOT, "dashboard", "data", "live_api.json")
STAGED_PATH    = os.path.join(STAGING_DIR, "api_from_hdfs.json")

# Interval antar siklus (detik). Override: set env var SPARK_INTERVAL.
INTERVAL_SECONDS  = int(os.getenv("SPARK_INTERVAL",    "60"))
# Jalankan ML setiap N siklus (lebih jarang agar loop tidak lambat)
ML_EVERY_N_CYCLES = int(os.getenv("SPARK_ML_EVERY",   "5"))

HDFS_GLOB = "/data/gempa/api/*.json"   # path di dalam HDFS container

# Cache hasil ML terakhir (dipakai di siklus tanpa re-training)
_last_ml_result: dict = {"status": "pending"}

# ─── Spark session — dibuat SEKALI, hidup selamanya ──────────────────────────
print("Memulai Spark session…")
spark = (
    SparkSession.builder
    .appName("GempaRadar-Continuous")
    .config("spark.sql.legacy.timeParserPolicy", "LEGACY")
    .config("spark.driver.memory", os.getenv("SPARK_DRIVER_MEMORY", "1g"))
    # Tidak ada konfigurasi HDFS → Spark tidak mencoba koneksi ke DataNode
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")
print("Spark session aktif.\n")


# ─── Helper: ambil data dari HDFS via docker exec ────────────────────────────

def fetch_from_hdfs_bridge() -> str:
    """
    Jalankan:  docker exec hadoop-namenode hdfs dfs -cat /data/gempa/api/*.json
    dan simpan hasilnya ke STAGING_DIR/api_from_hdfs.json.
    Return path file lokal yang berisi data.
    Raise Exception jika gagal atau hasilnya kosong.
    """
    result = subprocess.run(
        ["docker", "exec", "hadoop-namenode", "sh", "-lc",
         f"hdfs dfs -cat {HDFS_GLOB}"],
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"docker exec gagal (rc={result.returncode}): "
            f"{result.stderr.decode(errors='replace')[:300]}"
        )
    raw = result.stdout
    if not raw.strip():
        raise RuntimeError("HDFS bridge mengembalikan data kosong")
    with open(STAGED_PATH, "wb") as fh:
        fh.write(raw)
    return STAGED_PATH


def save_result_to_hdfs(records, hdfs_dir: str, filename: str):
    """Simpan hasil analisis ke HDFS via docker cp + hdfs dfs -put."""
    local_path    = os.path.join(STAGING_DIR, filename)
    container_tmp = f"/tmp/{filename}"
    with open(local_path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, ensure_ascii=False, indent=2)
    subprocess.run(
        ["docker", "cp", local_path, f"hadoop-namenode:{container_tmp}"],
        check=True, capture_output=True, timeout=15,
    )
    subprocess.run(
        ["docker", "exec", "hadoop-namenode", "hdfs", "dfs", "-mkdir", "-p", hdfs_dir],
        check=True, capture_output=True, timeout=15,
    )
    subprocess.run(
        ["docker", "exec", "hadoop-namenode", "hdfs", "dfs",
         "-put", "-f", container_tmp, f"{hdfs_dir}/{filename}"],
        check=True, capture_output=True, timeout=15,
    )


def rows_to_dicts(frame):
    return [row.asDict(recursive=True) for row in frame.collect()]


# ─── Load data — dipanggil setiap siklus ─────────────────────────────────────

def load_data():
    """
    Coba HDFS bridge → file lokal.
    Return (DataFrame, source_label).
    """
    # 1. HDFS via docker bridge
    try:
        data_path = fetch_from_hdfs_bridge()
        uri = "file:///" + os.path.abspath(data_path).replace("\\", "/")
        frame = spark.read.option("multiLine", True).json(uri)
        count = frame.count()
        if count == 0:
            raise RuntimeError("Bridge berhasil tapi data kosong")
        print(f"  [DATA] HDFS bridge: {count} record")
        return frame, "bridge"
    except Exception as exc:
        print(f"  [WARN] HDFS bridge gagal: {exc}")

    # 2. File lokal live_api.json
    if not os.path.exists(LOCAL_PATH):
        raise FileNotFoundError(
            f"Tidak ada sumber data: file lokal tidak ditemukan ({LOCAL_PATH})"
        )
    uri = "file:///" + os.path.abspath(LOCAL_PATH).replace("\\", "/")
    frame = spark.read.option("multiLine", True).json(uri)
    count = frame.count()
    if count == 0:
        raise RuntimeError("File lokal ditemukan tapi kosong")
    print(f"  [DATA] File lokal: {count} record")
    return frame, "local"


# ─── Satu siklus analisis ────────────────────────────────────────────────────

def run_analysis_cycle(cycle: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print()
    print("=" * 60)
    print(f"  Siklus #{cycle}  —  {now}")
    print("=" * 60)

    # Load data
    try:
        df, source = load_data()
    except Exception as exc:
        print(f"  [ERROR] Gagal load data: {exc}")
        return  # lewati siklus ini, tunggu interval berikutnya

    df.createOrReplaceTempView("gempa")

    # ── Analisis SQL ──────────────────────────────────────────────────────
    mag_dist = spark.sql("""
        SELECT
            CASE
                WHEN magnitude < 3                        THEN 'Mikro (M<3)'
                WHEN magnitude >= 3 AND magnitude < 4    THEN 'Minor (M3-4)'
                WHEN magnitude >= 4 AND magnitude < 5    THEN 'Sedang (M4-5)'
                WHEN magnitude >= 5                       THEN 'Kuat (M>=5)'
                ELSE 'Tidak diketahui'
            END AS kategori,
            COUNT(*)                  AS jumlah,
            ROUND(AVG(magnitude), 2)  AS avg_mag,
            ROUND(MAX(magnitude), 2)  AS max_mag
        FROM gempa
        WHERE magnitude IS NOT NULL
        GROUP BY 1
        ORDER BY jumlah DESC
    """)

    stats = spark.sql("""
        SELECT
            COUNT(*)                                           AS total_gempa,
            ROUND(AVG(magnitude), 2)                          AS avg_magnitude,
            ROUND(MAX(magnitude), 2)                          AS max_magnitude,
            ROUND(MIN(magnitude), 2)                          AS min_magnitude,
            SUM(CASE WHEN magnitude >= 5 THEN 1 ELSE 0 END)  AS gempa_kuat
        FROM gempa
        WHERE magnitude IS NOT NULL
    """)

    wilayah = spark.sql("""
        SELECT
            CASE
                WHEN lokasi LIKE '% of %' THEN trim(split(lokasi, ' of ')[1])
                ELSE coalesce(lokasi, 'Unknown')
            END AS wilayah,
            COUNT(*)                  AS jumlah_gempa,
            ROUND(AVG(magnitude), 2)  AS avg_mag,
            ROUND(MAX(magnitude), 2)  AS max_mag
        FROM gempa
        WHERE lokasi IS NOT NULL
        GROUP BY 1
        ORDER BY jumlah_gempa DESC
        LIMIT 10
    """)

    depth_dist = spark.sql("""
        SELECT
            CASE
                WHEN kedalaman_km < 70                         THEN 'Dangkal (<70 km)'
                WHEN kedalaman_km >= 70 AND kedalaman_km < 300 THEN 'Menengah (70-300 km)'
                ELSE 'Dalam (>300 km)'
            END AS kategori_kedalaman,
            COUNT(*)                    AS jumlah,
            ROUND(AVG(kedalaman_km), 1) AS avg_depth,
            ROUND(AVG(magnitude), 2)    AS avg_magnitude
        FROM gempa
        WHERE kedalaman_km IS NOT NULL
        GROUP BY 1
        ORDER BY jumlah DESC
    """)

    korelasi = spark.sql("""
        SELECT ROUND(CORR(magnitude, kedalaman_km), 4) AS korelasi_mag_depth
        FROM gempa
        WHERE magnitude IS NOT NULL AND kedalaman_km IS NOT NULL
    """)

    # ── ML: Random Forest via scikit-learn (lebih cepat untuk dataset kecil) ──
    global _last_ml_result
    if cycle % ML_EVERY_N_CYCLES == 1:   # siklus 1, 6, 11, …
        print(f"  [ML] Menjalankan RandomForest sklearn (siklus #{cycle})…")
        try:
            import numpy as np
            from sklearn.ensemble import RandomForestClassifier as SkRF
            from sklearn.metrics import accuracy_score
            from sklearn.model_selection import train_test_split

            # Collect kolom yang dibutuhkan ke Python
            rows = df.select(
                "kedalaman_km", "longitude", "latitude", "magnitude"
            ).dropna().collect()

            if len(rows) >= 10:
                X = np.array([[r.kedalaman_km, r.longitude, r.latitude] for r in rows])
                y = np.array([1 if r.magnitude >= 5 else 0 for r in rows])
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, test_size=0.2, random_state=42
                )
                if len(X_test) > 0:
                    clf = SkRF(n_estimators=50, random_state=42, n_jobs=1)
                    clf.fit(X_train, y_train)
                    acc = accuracy_score(y_test, clf.predict(X_test))
                    _last_ml_result = {
                        "status":   "success",
                        "accuracy": round(float(acc), 4),
                        "model":    "RandomForest (sklearn)",
                        "n_total":  len(rows),
                    }
                else:
                    _last_ml_result = {"status": "insufficient_data", "n_total": len(rows)}
            else:
                _last_ml_result = {"status": "insufficient_data", "n_total": len(rows)}
        except Exception as exc:
            _last_ml_result = {"status": "error", "message": str(exc)}
        print(f"  [ML] Selesai: {_last_ml_result}")
    else:
        next_ml = ((cycle - 1) // ML_EVERY_N_CYCLES + 1) * ML_EVERY_N_CYCLES + 1
        print(f"  [ML] Pakai cache (ML berikutnya: siklus #{next_ml})")
    ml_result = _last_ml_result

    # ── Time-series ───────────────────────────────────────────────────────
    df_time = (
        df.withColumn("ts", to_timestamp(F.col("time_utc"), "yyyy-MM-dd HH:mm:ss 'UTC'"))
          .withColumn("tanggal", date_format("ts", "yyyy-MM-dd"))
          .withColumn("jam",     spark_hour("ts"))
    )
    daily = (
        df_time.groupBy("tanggal")
        .agg(
            F.count("*").alias("jumlah_gempa"),
            F.round(F.avg("magnitude"), 2).alias("avg_magnitude"),
            F.sum(when(F.col("magnitude") >= 5, 1).otherwise(0)).alias("gempa_kuat"),
        )
        .orderBy("tanggal", ascending=False)
    )
    hourly = (
        df_time.groupBy("jam")
        .agg(
            F.count("*").alias("frekuensi"),
            F.round(F.avg("magnitude"), 2).alias("avg_mag"),
        )
        .orderBy("jam")
    )

    # ── Simpan hasil analisis ke HDFS (opsional, hanya saat bridge tersedia) ─
    if source == "bridge":
        bridge_outputs = [
            (rows_to_dicts(mag_dist),   "/data/gempa/hasil/mag_dist", "mag_dist.json"),
            (rows_to_dicts(wilayah),    "/data/gempa/hasil/wilayah",  "wilayah.json"),
            (rows_to_dicts(depth_dist), "/data/gempa/hasil/depth",    "depth.json"),
            (rows_to_dicts(daily),      "/data/gempa/hasil/daily",    "daily.json"),
        ]
        for records, hdfs_dir, filename in bridge_outputs:
            try:
                save_result_to_hdfs(records, hdfs_dir, filename)
                print(f"  [HDFS] {hdfs_dir}/{filename} ✓")
            except Exception as exc:
                print(f"  [WARN] Gagal simpan HDFS {filename}: {exc}")

    # ── Simpan spark_results.json untuk dashboard ─────────────────────────
    os.makedirs(os.path.join(PROJECT_ROOT, "dashboard", "data"), exist_ok=True)
    output = {
        "generated_at":            datetime.now().isoformat(),
        "cycle":                   cycle,
        "data_source":             source,
        "analisis1_mag_dist":      rows_to_dicts(mag_dist),
        "analisis1_stats":         rows_to_dicts(stats),
        "analisis2_wilayah":       rows_to_dicts(wilayah),
        "analisis3_depth":         rows_to_dicts(depth_dist),
        "analisis3_korelasi":      rows_to_dicts(korelasi),
        "bonus_ml":                ml_result,
        "bonus_historical_daily":  rows_to_dicts(daily),
        "bonus_historical_hourly": rows_to_dicts(hourly),
    }
    out_path = os.path.join(PROJECT_ROOT, "dashboard", "data", "spark_results.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2, default=str)

    total = rows_to_dicts(stats)[0].get("total_gempa", "?")
    print(f"  [OK] spark_results.json diperbarui  |  total gempa: {total}  |  sumber: {source}")


# ─── Main loop ────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  GempaRadar — Spark Continuous Analysis")
    print(f"  Interval: setiap {INTERVAL_SECONDS} detik")
    print("  Tekan Ctrl+C untuk berhenti.")
    print("=" * 60)

    cycle = 0
    while True:
        cycle += 1
        try:
            run_analysis_cycle(cycle)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"  [ERROR] Siklus #{cycle} gagal tak terduga: {exc}")

        print(f"\n  Menunggu {INTERVAL_SECONDS} detik…  (siklus berikutnya: #{cycle + 1})")
        try:
            time.sleep(INTERVAL_SECONDS)
        except KeyboardInterrupt:
            raise


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Dihentikan oleh pengguna (Ctrl+C).")
    finally:
        print("[INFO] Menghentikan Spark session…")
        spark.stop()
        print("[INFO] Selesai.")