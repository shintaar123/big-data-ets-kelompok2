# GempaRadar — Big Data Earthquake Monitoring Pipeline

**Mata Kuliah:** Big Data dan Data Lakehouse  
**Evaluasi:** Evaluasi Tengah Semester (ETS) 
**Topik:** Topik 6 — Monitor Aktivitas Seismik Wilayah Indonesia  

---

## Anggota Kelompok dan Kontribusi

| Nama | Role | Deskripsi Tugas |
|------|------|-----------------|
| Hafiz Ramadhan (5027241096) | DevOps & Infrastruktur | Menyiapkan dan menjalankan infrastruktur menggunakan Docker Compose untuk Hadoop (Namenode & Datanode) dan Kafka (Zookeeper & Broker). Mengatur Docker network, variabel environment (hadoop.env), serta membuat struktur direktori awal di HDFS (`/data/gempa/api`, `/data/gempa/rss`, `/data/gempa/hasil`). |
| Zaenal Mustofa (5027241018) | Kafka Producer API | Membuat `kafka/producer_api.py` untuk mengambil data gempa terbaru secara otomatis dari USGS Earthquake FDSN API setiap 5 menit, memformat response GeoJSON menjadi event JSON konsisten, dan mengirimkannya ke topic Kafka `gempa-api` dengan key berupa ID unik gempa. |
| Salsa Bil Ulla (5027241052) | RSS Producer & Consumer HDFS | Membuat `kafka/producer_rss.py` untuk mengambil berita gempa dari RSS feed secara berkala dengan pencegahan duplikasi via persistent cache; serta `kafka/consumer_to_hdfs.py` untuk membaca dari kedua topic Kafka secara paralel (threading), dan menyimpan data ke HDFS maupun file lokal dashboard. |
| Angga Firmansyah (5027241062) | Spark Analysis | Membuat `spark/analysis.py` untuk memproses data gempa dari HDFS menggunakan DataFrame API dan Spark SQL. Analisis mencakup distribusi magnitudo, top 10 wilayah aktif, korelasi kedalaman-magnitudo, pemodelan prediktif dengan Spark MLlib (RandomForest), serta tren aktivitas harian dan per jam. Output disimpan ke `spark_results.json`. |
| Shinta Alya Ramadani (5027241016) | Flask Dashboard | Membangun `dashboard/app.py` dan `dashboard/templates/index.html` sebagai antarmuka monitoring berbasis web. Menampilkan peta gempa interaktif (Leaflet.js), statistik ringkasan, 4 grafik analisis (Chart.js), live feed gempa terbaru, panel prediksi MLlib, dan berita RSS terkini dengan auto-refresh setiap 30 detik. |

---

## Topik dan Justifikasi

**Topik 6 — GempaRadar: Monitor Aktivitas Seismik Wilayah Indonesia**

Sistem ini dibangun untuk mensimulasikan kebutuhan BPBD (Badan Penanggulangan Bencana Daerah) yang memerlukan monitoring gempa bumi secara real-time sebagai dasar koordinasi respons kebencanaan. Indonesia berada di Cincin Api Pasifik dengan aktivitas seismik sangat tinggi, sehingga sistem monitoring berbasis Big Data menjadi relevan secara praktis.

Data gempa diambil dari USGS Earthquake FDSN API yang mencakup seluruh bounding box wilayah Indonesia (lintang -11 s.d. 6, bujur 95 s.d. 141), dipadukan dengan berita kebencanaan dari RSS feed nasional.

---

## Arsitektur Sistem

```
+------------------------------+       +---------------------------+
|  Sumber Data 1               |       |  Sumber Data 2            |
|  USGS Earthquake FDSN API    |       |  RSS Feed (Kompas / CNN)  |
|  (setiap 5 menit)            |       |  (setiap 5 menit)         |
+-------------+----------------+       +------------+--------------+
              |                                     |
              v                                     v
  +---------------------+               +---------------------+
  |  producer_api.py    |               |  producer_rss.py    |
  |  Topic: gempa-api   |               |  Topic: gempa-rss   |
  +----------+----------+               +----------+----------+
             |                                     |
             +------------------+------------------+
                                |
                                v
                   +------------------------+
                   |    Apache Kafka        |
                   |  (Docker: kafka-broker)|
                   +----------+-------------+
                              |
                              v
                   +------------------------+
                   |  consumer_to_hdfs.py   |
                   |  (threading, 2 topic)  |
                   +----------+-------------+
                              |
              +---------------+----------------+
              |                                |
              v                                v
  /data/gempa/api/*.json          /data/gempa/rss/*.json
  +--------------------------------+
  |       Hadoop HDFS              |
  |  (Docker: hadoop-namenode)     |
  +----------+---------------------+
             |
             v
  +---------------------------+
  |   spark/analysis.py       |
  |   3 Analisis Wajib        |
  |   + Bonus MLlib           |
  +----------+----------------+
             |
             v
  dashboard/data/spark_results.json
  dashboard/data/live_api.json
  dashboard/data/live_rss.json
             |
             v
  +---------------------------+
  |   dashboard/app.py        |
  |   Flask  localhost:5000   |
  +---------------------------+
```

| Teknologi | Peran |
|-----------|-------|
| Apache Kafka | Ingestion layer — menerima data dari API dan RSS secara real-time |
| Hadoop HDFS | Storage layer — menyimpan semua event sebagai JSON bertimestamp |
| Apache Spark | Processing layer — analisis batch dari HDFS, output ke JSON |
| Flask Dashboard | Serving layer — menampilkan hasil Spark dan data live ke browser |

---

## Struktur Repository

```
big-data-ets-kafka/
├── README.md
├── docker-compose-hadoop.yml
├── docker-compose-kafka.yml
├── hadoop.env
├── requirements.txt
├── HOWTORUN.md
│
├── kafka/
│   ├── producer_api.py          <- Polling USGS API, kirim ke gempa-api
│   ├── producer_rss.py          <- Polling RSS feed, kirim ke gempa-rss
│   └── consumer_to_hdfs.py      <- Konsumsi kedua topic, simpan ke HDFS
│
├── spark/
│   └── analysis.py              <- 3 analisis wajib + MLlib bonus
│
└── dashboard/
    ├── app.py                   <- Flask REST API (4 endpoint)
    ├── templates/
    │   └── index.html           <- UI dashboard + Chart.js + Leaflet
    ├── static/
    │   └── style.css
    └── data/                    <- Diisi saat sistem berjalan
        ├── spark_results.json
        ├── live_api.json
        └── live_rss.json
```

---

## Cara Menjalankan Sistem (End-to-End)

### Prasyarat

- Python 3.9+
- Docker Desktop aktif
- Git

### Langkah 1 — Clone dan Install Dependency

```bash
git clone <url-repo>
cd big-data-ets-kafka

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

### Langkah 2 — Buat Docker Network

```bash
docker network create hadoop_net
```

### Langkah 3 — Jalankan Kafka dan Hadoop

```bash
docker compose -f docker-compose-kafka.yml up -d
docker compose -f docker-compose-hadoop.yml up -d
```

Verifikasi semua container aktif:

```bash
docker ps
```

Container yang harus aktif: `kafka-broker`, `zookeeper`, `hadoop-namenode`, `hadoop-datanode`, `hadoop-resourcemanager`, `hadoop-nodemanager`.

### Langkah 4 — Buat Direktori HDFS

```bash
docker exec -it hadoop-namenode hdfs dfs -mkdir -p /data/gempa/api
docker exec -it hadoop-namenode hdfs dfs -mkdir -p /data/gempa/rss
docker exec -it hadoop-namenode hdfs dfs -mkdir -p /data/gempa/hasil
```

Verifikasi:

```bash
docker exec -it hadoop-namenode hdfs dfs -ls -R /data/gempa/
```

### Langkah 5 — Verifikasi Kafka Topic

```bash
docker exec -it kafka-broker kafka-topics.sh --list --bootstrap-server localhost:9092
```

Output yang diharapkan: `gempa-api` dan `gempa-rss` muncul dalam daftar.

### Langkah 6 — Jalankan Producer API

Terminal baru:

```bash
venv\Scripts\activate
python kafka/producer_api.py
```

Output yang diharapkan:

```
Producer API dimulai -> topic: gempa-api
[09:00:00] Mengambil data USGS...
  Gempa: M4.8 - 56 km SSE of Ternate, Indonesia
  Gempa: M4.3 - 23 km NW of Tobelo, Indonesia
  Sent: 8 event baru ke gempa-api
Menunggu 300 detik...
```

### Langkah 7 — Jalankan Producer RSS

Terminal baru:

```bash
venv\Scripts\activate
python kafka/producer_rss.py
```

Output yang diharapkan:

```
Producer RSS dimulai -> topic: gempa-rss
Backfill: 7 hari terakhir
[09:00:05] Mengambil RSS feed...
  Feed: Kompas Megapolitan — 22 artikel, 5 baru dikirim
  Feed: CNN Indonesia Nasional — 18 artikel, 3 baru dikirim
Menunggu 300 detik...
```

### Langkah 8 — Jalankan Consumer ke HDFS

Terminal baru:

```bash
venv\Scripts\activate
python kafka/consumer_to_hdfs.py
```

Consumer membaca dari kedua topic secara paralel menggunakan threading. Buffer di-flush ke HDFS setiap 2–5 menit. Setelah beberapa menit, verifikasi file masuk:

```bash
docker exec -it hadoop-namenode hdfs dfs -ls -R /data/gempa/
```

### Langkah 9 — Jalankan Spark Analysis

Terminal baru (jalankan setelah minimal 5 menit data terkumpul):

```bash
venv\Scripts\activate
python spark/analysis.py
```

Spark membaca dari HDFS secara default. Jika HDFS tidak dapat dijangkau, tersedia fallback ke `dashboard/data/live_api.json` dengan env var `ALLOW_LOCAL_FALLBACK=1` (tidak disarankan untuk penilaian).

Setelah selesai, file `dashboard/data/spark_results.json` akan dibuat/diperbarui.

### Langkah 10 — Jalankan Dashboard

Terminal baru:

```bash
venv\Scripts\activate
python dashboard/app.py
```

Buka browser: **http://localhost:5000**

---

## Verifikasi Komponen

### Kafka

```bash
# List topic
docker exec -it kafka-broker kafka-topics.sh --list --bootstrap-server localhost:9092

# Lihat event masuk (gempa-api)
docker exec -it kafka-broker kafka-console-consumer.sh \
  --topic gempa-api --from-beginning --bootstrap-server localhost:9092

# Lihat event masuk (gempa-rss)
docker exec -it kafka-broker kafka-console-consumer.sh \
  --topic gempa-rss --from-beginning --bootstrap-server localhost:9092

# Cek consumer group dan LAG
docker exec -it kafka-broker kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --group gemparadar-consumer
```

### HDFS

```bash
# List semua file
docker exec -it hadoop-namenode hdfs dfs -ls -R /data/gempa/

# Ukuran data
docker exec -it hadoop-namenode hdfs dfs -du -h /data/gempa/api/

# HDFS Web UI
# Buka: http://localhost:9870
```

---

## Screenshot

### 1. HDFS Web UI — File Browser

<img width="555" height="462" alt="image" src="https://github.com/user-attachments/assets/ceb998d4-5271-4f90-8a59-9ac1b3737450" />


### 2. HDFS Command Line — Verifikasi File

<img width="1264" height="447" alt="image" src="https://github.com/user-attachments/assets/8814dab5-3fd5-4b9a-8779-f1dc0a968afb" />


### 3. Kafka Console Consumer — Event Masuk Topic gempa-api

<img width="1435" height="449" alt="image" src="https://github.com/user-attachments/assets/83467fa1-65b2-4362-b645-66e711f86b49" />


### 4. Kafka Consumer Group — LAG Indicator

<img width="1446" height="200" alt="image" src="https://github.com/user-attachments/assets/ca3df1fb-9353-45a8-b9d8-d39986e03783" />


### 5. Spark Analysis — Terminal Output

<img width="1152" height="512" alt="image" src="https://github.com/user-attachments/assets/761d6a8d-f79e-4f67-a244-a4dab3765b76" />


### 6. Dashboard — Tampilan Utama (localhost:5000)
LIGHT MODE

<img width="1886" height="855" alt="image" src="https://github.com/user-attachments/assets/3e962743-7ca2-48e9-ae3c-c79c6e0ebc3c" />

<img width="1919" height="907" alt="image" src="https://github.com/user-attachments/assets/c9b650ae-bc27-4cc8-b595-1a258843cdea" />

DARK MODE

<img width="1895" height="864" alt="image" src="https://github.com/user-attachments/assets/3a592ee5-cde1-4ea7-beef-ee26145066e8" />

<img width="1892" height="899" alt="image" src="https://github.com/user-attachments/assets/f75ad138-d87f-4e35-a010-a09b9a528644" />


### 7. Dashboard — Charts dan Panel ML

<img width="1874" height="773" alt="image" src="https://github.com/user-attachments/assets/382d58bd-be77-4eb4-a011-b3aa074aa5d3" />


### 8. Dashboard — Panel Berita Terbaru

<img width="1544" height="377" alt="image" src="https://github.com/user-attachments/assets/f0faffbc-b531-4ef7-94e8-797475f5f3c5" />

---

## Analisis Spark

Spark membaca seluruh file JSON dari direktori `hdfs://namenode:8020/data/gempa/api/` menggunakan `spark.read.option("multiLine", True).json(...)`. Data didaftarkan sebagai temporary view `gempa` untuk query Spark SQL.

### Analisis 1 — Distribusi Magnitudo

Mengelompokkan semua event gempa ke dalam 4 kategori: Mikro (M < 3), Minor (M 3–4), Sedang (M 4–5), dan Kuat (M ≥ 5). Menghitung jumlah, rata-rata, dan magnitudo tertinggi per kategori.

Berdasarkan data yang terkumpul, mayoritas gempa di wilayah Indonesia berada di kategori Sedang (M 4–5) sebanyak 18 kejadian dari total 20 event yang tercatat, dengan 2 kejadian masuk kategori Kuat (M ≥ 5). Ini mengindikasikan aktivitas seismik yang konsisten di level menengah.

### Analisis 2 — Wilayah Paling Aktif

Mengekstrak nama wilayah dari field `place` (substring setelah "of " jika ada), kemudian `groupBy` wilayah untuk menghitung frekuensi kejadian, rata-rata magnitudo, dan magnitudo tertinggi. Diurutkan descending untuk mendapatkan top 10.

Wilayah paling aktif berdasarkan data: Ternate, Bitung, Tual, dan Lospalos (Timor Leste). Ini sesuai dengan letak geografis lempeng Indo-Australia dan lempeng Pasifik yang bertemu di kawasan Maluku dan Papua.

### Analisis 3 — Distribusi Kedalaman

Mengelompokkan gempa ke 3 kategori kedalaman: Dangkal (< 70 km), Menengah (70–300 km), dan Dalam (> 300 km). Dihitung juga korelasi antara magnitudo dan kedalaman menggunakan Spark SQL.

Korelasi magnitudo-kedalaman menghasilkan nilai -0.59, mengindikasikan bahwa gempa yang lebih dangkal cenderung memiliki magnitudo lebih tinggi di dataset ini. Gempa dangkal (<70 km) berjumlah 8 kejadian dengan rata-rata magnitudo 4.73, lebih tinggi dibanding gempa dalam.

### Bonus — MLlib RandomForest Classifier

Model dlatih untuk memprediksi apakah suatu gempa akan mencapai magnitudo ≥ M5 berdasarkan fitur `depth` dan koordinat. Menggunakan `RandomForestClassifier` dari `pyspark.ml.classification`. Model berhasil dilatih dan dievaluasi dengan akurasi yang tersimpan di `spark_results.json` field `bonus_ml`.

---

## Fitur Dashboard

Dashboard dibangun dengan Flask sebagai backend dan HTML/CSS/JavaScript murni sebagai frontend tanpa framework tambahan.

**Backend (app.py) — 4 Endpoint:**

| Endpoint | Fungsi |
|----------|--------|
| `GET /` | Serve halaman index.html |
| `GET /api/results` | Return isi spark_results.json |
| `GET /api/live` | Return 20 gempa terbaru + 10 berita terbaru |
| `GET /api/data` | Return gabungan ketiga file data |
| `GET /api/status` | Cek ketersediaan file JSON |

**Frontend (index.html) — Panel:**

- **Stats Row:** 5 kartu angka (total gempa, rata-rata mag, gempa kuat, kedalaman rata-rata, risk level) yang diisi dari Spark results
- **Peta Interaktif (Leaflet.js):** Marker gempa berwarna berdasarkan magnitudo (hijau/kuning/merah), filter tombol M4-5 / M5+, popup detail saat marker diklik, fitur Shakemap (heatmap overlay menggunakan Leaflet.heat)
- **Live Feed:** Daftar 20 gempa terbaru dari `live_api.json`, klik item = peta otomatis zoom ke lokasi (fungsi flyTo)
- **4 Chart (Chart.js):** Distribusi magnitudo (dari Analisis 1), Top wilayah aktif dengan bar proporsional (dari Analisis 2), Distribusi kedalaman dengan korelasi (dari Analisis 3), Pola aktivitas per jam 24 jam terakhir (dari data bonus)
- **Panel MLlib:** Ring chart akurasi model RandomForest dengan animasi, nama model, target, dan fitur
- **Panel Berita:** 10 kartu berita terbaru dari `live_rss.json` dengan ikon otomatis berdasarkan kata kunci judul

**Fitur Tambahan:**
- Auto-refresh setiap 30 detik via `setInterval(fetchData, 30000)`
- Dark mode / Light mode toggle
- Push notification browser untuk gempa M ≥ 5 yang baru masuk

---

## Mode Simulasi (Tanpa Docker)

Untuk pengujian lokal tanpa Docker/HDFS:

```bash
# Validasi producer tanpa Kafka
set DRY_RUN=1
python kafka/producer_api.py
python kafka/producer_rss.py

# Simulasi HDFS ke folder lokal mock_hdfs/
set SIMULATE_HDFS=1
python kafka/consumer_to_hdfs.py

# Spark dengan fallback ke file lokal
set ALLOW_LOCAL_FALLBACK=1
python spark/analysis.py
```

Catatan: Mode simulasi hanya untuk pengembangan. Untuk penilaian ETS, sistem harus berjalan dengan Docker (HDFS dan Kafka aktif).

---

## Catatan Teknis

**RSS Feed:** URL asli BMKG (`https://www.bmkg.go.id/rss/gempa_m50.xml`) dan Tempo RSS sudah tidak dapat diakses (HTTP 404) pada saat pengerjaan. Feed diganti ke Kompas Megapolitan dan CNN Indonesia Nasional yang tetap aktif dan berformat RSS valid. Kedua feed mencakup berita nasional termasuk laporan gempa ketika terjadi. Penggantian ini didokumentasikan sesuai ketentuan FAQ ETS.

**Producer RSS:** Menggunakan persistent cache file `.rss_cache.json` yang tetap tersimpan antar restart. Setiap artikel diidentifikasi via URL-nya sehingga tidak ada duplikasi meskipun producer di-restart. Mendukung backfill artikel hingga 7 hari ke belakang.

**Spark HDFS Fallback:** `analysis.py` mencoba tiga strategi secara berurutan: (1) baca langsung dari HDFS via SparkSession, (2) bridge melalui `hdfs dfs -cat` dan staging ke file lokal sementara, (3) baca dari `live_api.json` sebagai fallback terakhir. Strategi fallback hanya aktif jika HDFS tidak dapat dijangkau.

---

## Tantangan dan Solusi

**1. RSS Feed BMKG tidak dapat diakses**

RSS feed resmi BMKG dan Tempo yang disebutkan di soal mengembalikan HTTP 404. Solusinya adalah mencari feed alternatif yang aktif dan valid secara format RSS, yaitu Kompas dan CNN Indonesia, kemudian mendokumentasikan penggantian ini di README sesuai arahan FAQ ETS.

**2. Koneksi Spark ke HDFS**

Spark tidak selalu bisa menjangkau HDFS di dalam Docker dari host secara langsung karena hostname resolusi berbeda. Solusinya adalah menambahkan konfigurasi `spark.hadoop.fs.defaultFS` secara eksplisit dan membuat fallback dua lapis (bridge via subprocess, lalu fallback lokal) agar Spark tetap bisa berjalan dalam kondisi apapun.

**3. Kafka `enable_idempotence` kompatibilitas**

Beberapa versi `kafka-python` tidak mendukung parameter `enable_idempotence` secara langsung. Solusinya adalah membungkus inisialisasi producer dalam try-except: jika `enable_idempotence=True` gagal, producer dibuat ulang tanpa parameter tersebut namun tetap dengan `acks="all"`.

**4. Duplikasi event RSS**

Producer RSS yang di-restart akan membaca ulang feed dari awal dan berpotensi mengirim artikel yang sama ke Kafka. Solusinya adalah menyimpan semua URL yang sudah dikirim ke file JSON persistent (`.rss_cache.json`) yang tetap ada antar sesi, sehingga duplikasi dicegah pada level producer.

**5. Volume data Spark kecil di awal**

Saat pertama kali dijalankan, belum banyak data di HDFS sehingga analisis Spark menghasilkan dataset kecil. Solusinya adalah menjalankan producer minimal selama beberapa jam sebelum menjalankan Spark, dan menambahkan fitur backfill RSS 7 hari untuk memperkaya dataset berita sejak awal.

---
## Referensi

**Data & API**
- USGS Earthquake FDSN Event Web Service — https://earthquake.usgs.gov/fdsnws/event/1/
- USGS GeoJSON Feed Documentation — https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
- Kompas RSS Feed — https://rss.kompas.com/feed/kompas.com/megapolitan
- CNN Indonesia RSS Feed — https://www.cnnindonesia.com/nasional/rss

**Teknologi & Dokumentasi Resmi**
- Apache Kafka Documentation — https://kafka.apache.org/documentation/
- kafka-python Library — https://kafka-python.readthedocs.io/
- Apache Hadoop HDFS — https://hadoop.apache.org/docs/stable/hadoop-project-dist/hadoop-hdfs/HdfsUserGuide.html
- Apache Spark Documentation — https://spark.apache.org/docs/latest/
- PySpark DataFrame API — https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql.html
- Spark MLlib Guide — https://spark.apache.org/docs/latest/ml-guide.html
- Flask Documentation — https://flask.palletsprojects.com/
- Leaflet.js — https://leafletjs.com/
- Chart.js — https://www.chartjs.org/docs/latest/
- Leaflet.heat Plugin — https://github.com/Leaflet/Leaflet.heat

**Materi Perkuliahan**
- Materi P4 — Hadoop/HDFS & Docker Compose
- Materi P5 — Apache Spark & PySpark
- Materi P8 — Apache Kafka & Streaming Pipeline

**Tools & Library Tambahan**
- feedparser — https://feedparser.readthedocs.io/
- Docker Documentation — https://docs.docker.com/

## 📝 REVISI: Spark Analysis → Continuous Mode

> **Alasan revisi:** Sesuai arahan dosen, Spark analysis harus berjalan **otomatis dan kontinu** — bukan one-shot batch yang harus dijalankan ulang manual setiap kali ada data baru. Revisi ini membuat Spark session tetap hidup dan me-reload data dari HDFS secara berkala.

### Ringkasan Perubahan

| Aspek | Sebelum (v1) | Sesudah (v2 — Revisi) |
|-------|-------------|----------------------|
| Mode eksekusi | One-shot batch (jalankan sekali, selesai) | **Continuous loop** (analisis ulang setiap 60 detik) |
| Spark session | Dibuat dan di-stop setiap kali run | Dibuat **sekali**, hidup selamanya sampai Ctrl+C |
| Sumber data HDFS | Langsung via `spark.read.json("hdfs://...")` | **Docker bridge** (`docker exec hdfs dfs -cat`) → file staging lokal |
| ML model | Spark MLlib `RandomForestClassifier` | **scikit-learn** `RandomForestClassifier` (lebih cepat untuk dataset kecil) |
| ML frekuensi | Setiap kali run | Setiap **5 siklus** (`ML_EVERY_N_CYCLES`), hasil di-cache |
| Hasil analisis | Disimpan sekali ke `spark_results.json` | **Diperbarui terus** setiap siklus |
| Hasil ke HDFS | Tidak | Hasil analisis juga disimpan ke `/data/gempa/hasil/` di HDFS |
| Dependency baru | — | `scikit-learn` (tambah ke pip install) |

### File yang Diubah

#### 1. `spark/analysis.py` — Rewrite Total

Perubahan utama pada file ini:

**a) Continuous Loop**
```python
# SEBELUM: one-shot
if __name__ == "__main__":
    # ... jalankan analisis sekali ...
    spark.stop()

# SESUDAH: continuous loop
def main():
    cycle = 0
    while True:
        cycle += 1
        run_analysis_cycle(cycle)
        time.sleep(INTERVAL_SECONDS)  # default: 60 detik

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Dihentikan oleh pengguna.")
    finally:
        spark.stop()
```

**b) HDFS Docker Bridge (bukan koneksi langsung)**
```python
# SEBELUM: Spark langsung baca HDFS (sering gagal dari Windows host)
df = spark.read.json("hdfs://namenode:8020/data/gempa/api/")

# SESUDAH: Docker bridge — cat dari container, simpan ke file staging
def fetch_from_hdfs_bridge():
    result = subprocess.run(
        ["docker", "exec", "hadoop-namenode", "sh", "-lc",
         "hdfs dfs -cat /data/gempa/api/*.json"],
        capture_output=True, timeout=30,
    )
    # Simpan ke tmp/spark_bridge/api_from_hdfs.json
    with open(STAGED_PATH, "wb") as fh:
        fh.write(result.stdout)
    return STAGED_PATH

# Spark baca dari file staging lokal
df = spark.read.option("multiLine", True).json("file:///..." + staged_path)
```

**c) ML: scikit-learn menggantikan Spark MLlib**
```python
# SEBELUM: Spark MLlib (lambat untuk dataset kecil, sering error)
from pyspark.ml.classification import RandomForestClassifier
# ... VectorAssembler, Pipeline, dll

# SESUDAH: scikit-learn (cepat, stabil)
from sklearn.ensemble import RandomForestClassifier as SkRF
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

# Hanya dijalankan setiap 5 siklus untuk performa
if cycle % ML_EVERY_N_CYCLES == 1:
    rows = df.select("kedalaman_km", "longitude", "latitude", "magnitude").dropna().collect()
    X = np.array([[r.kedalaman_km, r.longitude, r.latitude] for r in rows])
    y = np.array([1 if r.magnitude >= 5 else 0 for r in rows])
    clf = SkRF(n_estimators=50, random_state=42)
    clf.fit(X_train, y_train)
    acc = accuracy_score(y_test, clf.predict(X_test))
```

**d) Simpan hasil analisis ke HDFS**
```python
# BARU: Hasil analisis juga ditulis balik ke HDFS
def save_result_to_hdfs(records, hdfs_dir, filename):
    # docker cp local_file hadoop-namenode:/tmp/file
    # docker exec hadoop-namenode hdfs dfs -put -f /tmp/file hdfs_dir/
    ...

# Output ke HDFS:
# /data/gempa/hasil/mag_dist/mag_dist.json
# /data/gempa/hasil/wilayah/wilayah.json
# /data/gempa/hasil/depth/depth.json
# /data/gempa/hasil/daily/daily.json
```

**e) Konfigurasi via Environment Variable**

| Variable | Default | Fungsi |
|----------|---------|--------|
| `SPARK_INTERVAL` | `60` | Interval antar siklus (detik) |
| `SPARK_ML_EVERY` | `5` | Jalankan ML setiap N siklus |
| `SPARK_DRIVER_MEMORY` | `1g` | Memori driver Spark |

#### 2. `requirements.txt` — Tambah scikit-learn

```diff
 kafka-python-ng
 requests==2.31.0
 feedparser==6.0.11
 flask==3.0.3
 pyspark==3.5.1
 numpy>=1.26,<3
 python-dateutil==2.8.2
+scikit-learn
```

> **Catatan:** `scikit-learn` perlu di-install manual: `pip install scikit-learn`

### Cara Menjalankan (Revisi)

Langkah sama seperti sebelumnya, tapi pada **TAHAP Spark**:

```powershell
# Set Java 11 (WAJIB)
$env:JAVA_HOME = "C:\Program Files\Microsoft\jdk-11.0.30.7-hotspot"
$env:PATH = "$env:JAVA_HOME\bin;" + $env:PATH
$env:PYSPARK_PYTHON = (Get-Command python).Source
$env:PYSPARK_DRIVER_PYTHON = (Get-Command python).Source

.\venv\Scripts\Activate.ps1
python spark/analysis.py
```

**Perbedaan:** Spark sekarang **tidak berhenti sendiri**. Akan terus loop dan memperbarui `spark_results.json` setiap 60 detik. Tekan **Ctrl+C** untuk menghentikan.

Output contoh:
```
============================================================
  GempaRadar — Spark Continuous Analysis
  Interval: setiap 60 detik
  Tekan Ctrl+C untuk berhenti.
============================================================

============================================================
  Siklus #1  —  2026-05-13 09:10:00
============================================================
  [DATA] HDFS bridge: 20 record
  [ML] Menjalankan RandomForest sklearn (siklus #1)…
  [ML] Selesai: {'status': 'success', 'accuracy': 0.75, ...}
  [HDFS] /data/gempa/hasil/mag_dist/mag_dist.json ✓
  [HDFS] /data/gempa/hasil/wilayah/wilayah.json ✓
  [OK] spark_results.json diperbarui  |  total gempa: 20  |  sumber: bridge

  Menunggu 60 detik…  (siklus berikutnya: #2)
```
<img width="992" height="373" alt="image" src="https://github.com/user-attachments/assets/7a376b96-6eea-4678-a0a7-fae21fe6f217" />
