import os
import sys
import json
from datetime import datetime

# ── FIX WINDOWS: SET JAVA_HOME DI DALAM KODE ─────────────────
os.environ["JAVA_HOME"] = r"D:\JDK-17"
os.environ["PATH"] = r"D:\JDK-17\bin;" + os.environ.get("PATH", "")

# ── FIX WINDOWS: PATH SPASI ───────────────────────────────────
if sys.platform == "win32":
    import ctypes
    buf = ctypes.create_unicode_buffer(1024)

    # short path untuk python executable
    ctypes.windll.kernel32.GetShortPathNameW(sys.executable, buf, 1024)
    short_python = buf.value
    if short_python:
        os.environ["PYSPARK_PYTHON"] = short_python
        os.environ["PYSPARK_DRIVER_PYTHON"] = short_python

    # short path untuk pyspark
    import pyspark
    pyspark_dir = os.path.dirname(pyspark.__file__)
    ctypes.windll.kernel32.GetShortPathNameW(pyspark_dir, buf, 1024)
    short_pyspark = buf.value
    if short_pyspark:
        os.environ["SPARK_HOME"] = short_pyspark

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── IMPORT SPARK ──────────────────────────────────────────────
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import when, to_timestamp, date_format, hour as Hour

# ── INISIALISASI SPARK ────────────────────────────────────────
spark = (SparkSession.builder
    .appName("GempaRadar-Analysis")
    .config("spark.sql.legacy.timeParserPolicy", "LEGACY")
    .config("spark.driver.memory", "1g")
    .getOrCreate())
spark.sparkContext.setLogLevel("WARN")

print("=" * 60)
print("GempaRadar — Apache Spark Analysis")
print("=" * 60)

# ── LOAD DATA ─────────────────────────────────────────────────
HDFS_PATH  = "hdfs://localhost:8020/data/gempa/api"
LOCAL_PATH = os.path.join("dashboard", "data", "live_api.json")

def load_data():
    try:
        df = spark.read.option("multiLine", True).json(HDFS_PATH)
        count = df.count()
        if count == 0:
            raise Exception("HDFS kosong")
        print(f"✅ Data dari HDFS: {count} record")
        return df
    except Exception as e:
        print(f"[WARN] HDFS tidak bisa diakses: {e}")
        print("[INFO] Mencoba file lokal...")
        if not os.path.exists(LOCAL_PATH):
            print(f"[ERROR] File lokal juga tidak ada: {LOCAL_PATH}")
            print("[ERROR] Pastikan consumer sudah jalan minimal 2 menit!")
            spark.stop()
            sys.exit(1)
        df = spark.read.option("multiLine", True).json(LOCAL_PATH)
        count = df.count()
        print(f"✅ Data dari lokal: {count} record")
        return df

df = load_data()
df.createOrReplaceTempView("gempa")
df.printSchema()

# ── ANALISIS 1: DISTRIBUSI MAGNITUDO ─────────────────────────
print("\n" + "=" * 60)
print("ANALISIS 1: Distribusi Kategori Magnitudo")
print("=" * 60)

mag_dist = spark.sql("""
    SELECT
        CASE
            WHEN magnitude < 3              THEN 'Mikro (M<3)'
            WHEN magnitude BETWEEN 3 AND 4  THEN 'Minor (M3-4)'
            WHEN magnitude BETWEEN 4 AND 5  THEN 'Sedang (M4-5)'
            WHEN magnitude >= 5             THEN 'Kuat (M>=5)'
            ELSE 'Tidak diketahui'
        END AS kategori,
        COUNT(*) AS jumlah,
        ROUND(AVG(magnitude), 2) AS avg_mag,
        ROUND(MAX(magnitude), 2) AS max_mag
    FROM gempa
    WHERE magnitude IS NOT NULL
    GROUP BY kategori
    ORDER BY jumlah DESC
""")
mag_dist.show()

stats = spark.sql("""
    SELECT
        COUNT(*)                     AS total_gempa,
        ROUND(AVG(magnitude), 2)     AS avg_magnitude,
        ROUND(MAX(magnitude), 2)     AS max_magnitude,
        ROUND(MIN(magnitude), 2)     AS min_magnitude,
        SUM(CASE WHEN magnitude >= 5 THEN 1 ELSE 0 END) AS gempa_kuat
    FROM gempa
    WHERE magnitude IS NOT NULL
""")
stats.show()

# ── ANALISIS 2: WILAYAH PALING AKTIF ─────────────────────────
print("\n" + "=" * 60)
print("ANALISIS 2: Top 10 Wilayah Paling Aktif")
print("=" * 60)

wilayah = spark.sql("""
    SELECT
        CASE
            WHEN lokasi LIKE '% of %' THEN TRIM(SPLIT(lokasi, ' of ')[1])
            ELSE COALESCE(lokasi, 'Unknown')
        END AS wilayah,
        COUNT(*) AS jumlah_gempa,
        ROUND(AVG(magnitude), 2) AS avg_mag,
        ROUND(MAX(magnitude), 2) AS max_mag
    FROM gempa
    WHERE lokasi IS NOT NULL
    GROUP BY wilayah
    ORDER BY jumlah_gempa DESC
    LIMIT 10
""")
wilayah.show(truncate=False)

# ── ANALISIS 3: DISTRIBUSI KEDALAMAN ─────────────────────────
print("\n" + "=" * 60)
print("ANALISIS 3: Distribusi Kedalaman Gempa")
print("=" * 60)

depth_dist = spark.sql("""
    SELECT
        CASE
            WHEN kedalaman_km < 70  THEN 'Dangkal (<70 km)'
            WHEN kedalaman_km < 300 THEN 'Menengah (70-300 km)'
            ELSE 'Dalam (>300 km)'
        END AS kategori_kedalaman,
        COUNT(*) AS jumlah,
        ROUND(AVG(kedalaman_km), 1) AS avg_depth,
        ROUND(AVG(magnitude), 2)    AS avg_magnitude
    FROM gempa
    WHERE kedalaman_km IS NOT NULL
    GROUP BY kategori_kedalaman
    ORDER BY jumlah DESC
""")
depth_dist.show()

korelasi = spark.sql("""
    SELECT ROUND(CORR(magnitude, kedalaman_km), 4) AS korelasi_mag_depth
    FROM gempa
    WHERE magnitude IS NOT NULL AND kedalaman_km IS NOT NULL
""")
korelasi.show()

# ── BONUS 2: SPARK MLLIB ─────────────────────────────────────
print("\n" + "=" * 60)
print("BONUS 2: Predictive Model (Spark MLlib)")
print("=" * 60)

ml_result = {"status": "skipped"}
try:
    from pyspark.ml.feature import VectorAssembler
    from pyspark.ml.classification import RandomForestClassifier
    from pyspark.ml.evaluation import MulticlassClassificationEvaluator

    df_ml = df.filter(
        F.col("magnitude").isNotNull() &
        F.col("kedalaman_km").isNotNull() &
        F.col("longitude").isNotNull() &
        F.col("latitude").isNotNull()
    ).withColumn("label", when(F.col("magnitude") >= 5, 1.0).otherwise(0.0))

    assembler = VectorAssembler(
        inputCols=["kedalaman_km", "longitude", "latitude"],
        outputCol="features",
        handleInvalid="skip"
    )
    df_ml = assembler.transform(df_ml)
    train, test = df_ml.randomSplit([0.8, 0.2], seed=42)
    train_count = train.count()

    if train_count >= 10:
        rf    = RandomForestClassifier(
            featuresCol="features", labelCol="label",
            numTrees=50, seed=42
        )
        model = rf.fit(train)
        preds = model.transform(test)
        acc   = MulticlassClassificationEvaluator(
            labelCol="label", predictionCol="prediction",
            metricName="accuracy"
        ).evaluate(preds)
        print(f"✅ Random Forest Accuracy: {acc:.2%}")
        ml_result = {
            "status":   "success",
            "accuracy": round(acc, 4),
            "model":    "RandomForest"
        }
    else:
        print(f"[WARN] Data training hanya {train_count} record, minimal 10")
        ml_result = {"status": "insufficient_data", "train_count": train_count}

except Exception as e:
    print(f"[WARN] MLlib skip: {e}")
    ml_result = {"status": "error", "message": str(e)}

# ── BONUS 4: HISTORICAL + POLA JAM ───────────────────────────
print("\n" + "=" * 60)
print("BONUS 4: Pola Temporal")
print("=" * 60)

# FIX: format ISO 8601 dari producer_api.py
df_time = df.withColumn(
    "ts", to_timestamp(F.col("time_utc"))   # ← auto-detect ISO format
).withColumn(
    "tanggal", date_format("ts", "yyyy-MM-dd")
).withColumn(
    "jam", Hour("ts")
)

daily = df_time.groupBy("tanggal").agg(
    F.count("*").alias("jumlah_gempa"),
    F.round(F.avg("magnitude"), 2).alias("avg_magnitude"),
    F.sum(when(F.col("magnitude") >= 5, 1).otherwise(0)).alias("gempa_kuat"),
).orderBy("tanggal", ascending=False)
daily.show(10)

hourly = df_time.groupBy("jam").agg(
    F.count("*").alias("frekuensi"),
    F.round(F.avg("magnitude"), 2).alias("avg_mag"),
).orderBy("jam")
hourly.show(24)

# ── SIMPAN KE HDFS ────────────────────────────────────────────
print("\n[INFO] Menyimpan hasil ke HDFS...")
for result_df, path in [
    (mag_dist,   "hdfs://localhost:8020/data/gempa/hasil/mag_dist"),
    (wilayah,    "hdfs://localhost:8020/data/gempa/hasil/wilayah"),
    (depth_dist, "hdfs://localhost:8020/data/gempa/hasil/depth"),
    (daily,      "hdfs://localhost:8020/data/gempa/hasil/daily"),
]:
    try:
        result_df.coalesce(1).write.mode("overwrite").json(path)
        print(f"💾 HDFS OK: {path}")
    except Exception as e:
        print(f"[WARN] HDFS skip ({path}): {e}")

# ── SIMPAN spark_results.json UNTUK DASHBOARD ─────────────────
print("\n[INFO] Menyimpan spark_results.json...")
os.makedirs(os.path.join("dashboard", "data"), exist_ok=True)

output = {
    "generated_at":            datetime.now().isoformat(),
    "analisis1_mag_dist":      mag_dist.toPandas().to_dict(orient="records"),
    "analisis1_stats":         stats.toPandas().to_dict(orient="records"),
    "analisis2_wilayah":       wilayah.toPandas().to_dict(orient="records"),
    "analisis3_depth":         depth_dist.toPandas().to_dict(orient="records"),
    "analisis3_korelasi":      korelasi.toPandas().to_dict(orient="records"),
    "bonus_ml":                ml_result,
    "bonus_historical_daily":  daily.toPandas().to_dict(orient="records"),
    "bonus_historical_hourly": hourly.toPandas().to_dict(orient="records"),
}

out_path = os.path.join("dashboard", "data", "spark_results.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2, default=str)

print(f"\n✅ Semua hasil tersimpan di {out_path}")
spark.stop()