import json
import os
import subprocess
import sys
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAFE_TEMP_DIR = os.path.join(PROJECT_ROOT, ".spark_tmp")
os.makedirs(SAFE_TEMP_DIR, exist_ok=True)
os.environ["TEMP"] = SAFE_TEMP_DIR
os.environ["TMP"] = SAFE_TEMP_DIR
os.environ["SPARK_LOCAL_DIRS"] = os.path.join(SAFE_TEMP_DIR, "local")
os.makedirs(os.environ["SPARK_LOCAL_DIRS"], exist_ok=True)
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import date_format, hour as spark_hour, to_timestamp, when

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HDFS_HOST = os.getenv("HDFS_HOST", "localhost")
HDFS_PORT = os.getenv("HDFS_PORT", "8020")
HDFS_BASE = f"hdfs://{HDFS_HOST}:{HDFS_PORT}"
HDFS_PATH = f"{HDFS_BASE}/data/gempa/api"
HDFS_DATANODE_HOST = os.getenv("HDFS_DATANODE_HOST", "localhost")
HDFS_DATANODE_PORT = os.getenv("HDFS_DATANODE_PORT", "9866")
ALLOW_LOCAL_FALLBACK = os.getenv("ALLOW_LOCAL_FALLBACK", "0") == "1"
LOCAL_PATH = os.path.join("dashboard", "data", "live_api.json")
LOCAL_PATH_URI = "file:///" + os.path.abspath(LOCAL_PATH).replace("\\", "/")
STAGING_DIR = os.path.join(PROJECT_ROOT, "tmp", "spark_bridge")
os.makedirs(STAGING_DIR, exist_ok=True)

spark_builder = (
    SparkSession.builder.appName("GempaRadar-Analysis")
    .config("spark.sql.legacy.timeParserPolicy", "LEGACY")
    .config("spark.driver.memory", os.getenv("SPARK_DRIVER_MEMORY", "1g"))
)
spark_builder = spark_builder.config("spark.hadoop.fs.defaultFS", HDFS_BASE)
spark_builder = spark_builder.config("dfs.client.use.datanode.hostname", "false")
spark_builder = spark_builder.config("dfs.namenode.servicerpc-address", f"{HDFS_HOST}:{HDFS_PORT}")
spark = spark_builder.getOrCreate()
spark.sparkContext.setLogLevel("WARN")
USING_HDFS_SOURCE = False
USING_HDFS_BRIDGE = False


def stage_hdfs_json_glob_to_local(hdfs_glob: str, local_filename: str):
    local_path = os.path.join(STAGING_DIR, local_filename)
    command = [
        "docker",
        "exec",
        "hadoop-namenode",
        "sh",
        "-lc",
        f"hdfs dfs -cat {hdfs_glob}",
    ]
    result = subprocess.run(command, check=True, capture_output=True)
    with open(local_path, "wb") as file:
        file.write(result.stdout)
    return local_path


def save_json_records_to_hdfs(records, hdfs_dir: str, local_filename: str):
    local_path = os.path.join(STAGING_DIR, local_filename)
    container_tmp = f"/tmp/{local_filename}"
    with open(local_path, "w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)

    subprocess.run(
        ["docker", "cp", local_path, f"hadoop-namenode:{container_tmp}"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["docker", "exec", "hadoop-namenode", "hdfs", "dfs", "-mkdir", "-p", hdfs_dir],
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
            f"{hdfs_dir}/{local_filename}",
        ],
        check=True,
        capture_output=True,
    )


def load_data():
    global USING_HDFS_SOURCE, USING_HDFS_BRIDGE
    try:
        frame = spark.read.option("multiLine", True).json(HDFS_PATH)
        count = frame.count()
        if count == 0:
            raise RuntimeError("HDFS kosong")
        print(f"Data dari HDFS: {count} record")
        USING_HDFS_SOURCE = True
        USING_HDFS_BRIDGE = False
        return frame
    except Exception as exc:
        try:
            staged_local_path = stage_hdfs_json_glob_to_local("/data/gempa/api/*.json", "api_from_hdfs.json")
            staged_uri = "file:///" + os.path.abspath(staged_local_path).replace("\\", "/")
            frame = spark.read.option("multiLine", True).json(staged_uri)
            count = frame.count()
            if count == 0:
                raise RuntimeError("HDFS bridge menghasilkan 0 record")
            print(f"[INFO] Data dari HDFS bridge: {count} record")
            USING_HDFS_SOURCE = False
            USING_HDFS_BRIDGE = True
            return frame
        except Exception as bridge_exc:
            print(f"[WARN] HDFS bridge gagal: {bridge_exc}")

        if not ALLOW_LOCAL_FALLBACK:
            print(f"[ERROR] HDFS tidak bisa diakses: {exc}")
            print("[ERROR] Set ALLOW_LOCAL_FALLBACK=1 hanya untuk simulasi lokal")
            spark.stop()
            sys.exit(1)

        print(f"[WARN] HDFS tidak bisa diakses: {exc}")
        print("[INFO] Mencoba file lokal dashboard/data/live_api.json")
        if not os.path.exists(LOCAL_PATH):
            print(f"[ERROR] File lokal tidak ditemukan: {LOCAL_PATH}")
            spark.stop()
            sys.exit(1)

        frame = spark.read.option("multiLine", True).json(LOCAL_PATH_URI)
        print(f"Data dari lokal: {frame.count()} record")
        USING_HDFS_SOURCE = False
        USING_HDFS_BRIDGE = False
        return frame


def rows_to_dicts(frame):
    return [row.asDict(recursive=True) for row in frame.collect()]


df = load_data()
df.createOrReplaceTempView("gempa")

print("=" * 60)
print("GempaRadar - Apache Spark Analysis")
print("=" * 60)
df.printSchema()

mag_dist = spark.sql(
    """
    SELECT
        CASE
            WHEN magnitude < 3 THEN 'Mikro (M<3)'
            WHEN magnitude >= 3 AND magnitude < 4 THEN 'Minor (M3-4)'
            WHEN magnitude >= 4 AND magnitude < 5 THEN 'Sedang (M4-5)'
            WHEN magnitude >= 5 THEN 'Kuat (M>=5)'
            ELSE 'Tidak diketahui'
        END AS kategori,
        COUNT(*) AS jumlah,
        ROUND(AVG(magnitude), 2) AS avg_mag,
        ROUND(MAX(magnitude), 2) AS max_mag
    FROM gempa
    WHERE magnitude IS NOT NULL
    GROUP BY 1
    ORDER BY jumlah DESC
    """
)

stats = spark.sql(
    """
    SELECT
        COUNT(*) AS total_gempa,
        ROUND(AVG(magnitude), 2) AS avg_magnitude,
        ROUND(MAX(magnitude), 2) AS max_magnitude,
        ROUND(MIN(magnitude), 2) AS min_magnitude,
        SUM(CASE WHEN magnitude >= 5 THEN 1 ELSE 0 END) AS gempa_kuat
    FROM gempa
    WHERE magnitude IS NOT NULL
    """
)

wilayah = spark.sql(
    """
    SELECT
        CASE
            WHEN lokasi LIKE '% of %' THEN trim(split(lokasi, ' of ')[1])
            ELSE coalesce(lokasi, 'Unknown')
        END AS wilayah,
        COUNT(*) AS jumlah_gempa,
        ROUND(AVG(magnitude), 2) AS avg_mag,
        ROUND(MAX(magnitude), 2) AS max_mag
    FROM gempa
    WHERE lokasi IS NOT NULL
    GROUP BY 1
    ORDER BY jumlah_gempa DESC
    LIMIT 10
    """
)

depth_dist = spark.sql(
    """
    SELECT
        CASE
            WHEN kedalaman_km < 70 THEN 'Dangkal (<70 km)'
            WHEN kedalaman_km >= 70 AND kedalaman_km < 300 THEN 'Menengah (70-300 km)'
            ELSE 'Dalam (>300 km)'
        END AS kategori_kedalaman,
        COUNT(*) AS jumlah,
        ROUND(AVG(kedalaman_km), 1) AS avg_depth,
        ROUND(AVG(magnitude), 2) AS avg_magnitude
    FROM gempa
    WHERE kedalaman_km IS NOT NULL
    GROUP BY 1
    ORDER BY jumlah DESC
    """
)

korelasi = spark.sql(
    """
    SELECT ROUND(CORR(magnitude, kedalaman_km), 4) AS korelasi_mag_depth
    FROM gempa
    WHERE magnitude IS NOT NULL AND kedalaman_km IS NOT NULL
    """
)

ml_result = {"status": "skipped"}
try:
    from pyspark.ml.classification import RandomForestClassifier
    from pyspark.ml.evaluation import MulticlassClassificationEvaluator
    from pyspark.ml.feature import VectorAssembler

    df_ml = df.filter(
        F.col("magnitude").isNotNull()
        & F.col("kedalaman_km").isNotNull()
        & F.col("longitude").isNotNull()
        & F.col("latitude").isNotNull()
    ).withColumn("label", when(F.col("magnitude") >= 5, 1.0).otherwise(0.0))

    assembler = VectorAssembler(
        inputCols=["kedalaman_km", "longitude", "latitude"],
        outputCol="features",
        handleInvalid="skip",
    )
    df_ml = assembler.transform(df_ml)
    train, test = df_ml.randomSplit([0.8, 0.2], seed=42)

    if train.count() >= 10 and test.count() > 0:
        model = RandomForestClassifier(
            featuresCol="features",
            labelCol="label",
            numTrees=50,
            seed=42,
        ).fit(train)
        predictions = model.transform(test)
        accuracy = MulticlassClassificationEvaluator(
            labelCol="label",
            predictionCol="prediction",
            metricName="accuracy",
        ).evaluate(predictions)
        ml_result = {
            "status": "success",
            "accuracy": round(accuracy, 4),
            "model": "RandomForest",
        }
    else:
        ml_result = {"status": "insufficient_data"}
except Exception as exc:
    ml_result = {"status": "error", "message": str(exc)}

df_time = (
    df.withColumn("ts", to_timestamp(F.col("time_utc"), "yyyy-MM-dd HH:mm:ss 'UTC'"))
    .withColumn("tanggal", date_format("ts", "yyyy-MM-dd"))
    .withColumn("jam", spark_hour("ts"))
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

if USING_HDFS_SOURCE:
    for frame, path in [
        (mag_dist, f"{HDFS_BASE}/data/gempa/hasil/mag_dist"),
        (wilayah, f"{HDFS_BASE}/data/gempa/hasil/wilayah"),
        (depth_dist, f"{HDFS_BASE}/data/gempa/hasil/depth"),
        (daily, f"{HDFS_BASE}/data/gempa/hasil/daily"),
    ]:
        try:
            frame.coalesce(1).write.mode("overwrite").json(path)
            print(f"HDFS OK: {path}")
        except Exception as exc:
            print(f"[WARN] Gagal simpan ke HDFS {path}: {exc}")
elif USING_HDFS_BRIDGE:
    bridge_outputs = [
        (rows_to_dicts(mag_dist), "/data/gempa/hasil/mag_dist", "mag_dist.json"),
        (rows_to_dicts(wilayah), "/data/gempa/hasil/wilayah", "wilayah.json"),
        (rows_to_dicts(depth_dist), "/data/gempa/hasil/depth", "depth.json"),
        (rows_to_dicts(daily), "/data/gempa/hasil/daily", "daily.json"),
    ]
    for records, hdfs_dir, filename in bridge_outputs:
        try:
            save_json_records_to_hdfs(records, hdfs_dir, filename)
            print(f"HDFS bridge OK: {hdfs_dir}/{filename}")
        except Exception as exc:
            print(f"[WARN] Gagal simpan via HDFS bridge {hdfs_dir}/{filename}: {exc}")
else:
    print("[INFO] Output HDFS dilewati karena mode fallback lokal sedang aktif")

os.makedirs(os.path.join("dashboard", "data"), exist_ok=True)
output = {
    "generated_at": datetime.now().isoformat(),
    "analisis1_mag_dist": rows_to_dicts(mag_dist),
    "analisis1_stats": rows_to_dicts(stats),
    "analisis2_wilayah": rows_to_dicts(wilayah),
    "analisis3_depth": rows_to_dicts(depth_dist),
    "analisis3_korelasi": rows_to_dicts(korelasi),
    "bonus_ml": ml_result,
    "bonus_historical_daily": rows_to_dicts(daily),
    "bonus_historical_hourly": rows_to_dicts(hourly),
}

out_path = os.path.join("dashboard", "data", "spark_results.json")
with open(out_path, "w", encoding="utf-8") as file:
    json.dump(output, file, ensure_ascii=False, indent=2, default=str)

print(f"Hasil dashboard tersimpan di {out_path}")
spark.stop()
