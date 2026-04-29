# GempaRadar - Panduan Lengkap Menjalankan Proyek

> **GempaRadar** adalah pipeline monitoring gempa bumi real-time yang mengintegrasikan Kafka, Hadoop HDFS, Apache Spark, dan Flask Dashboard. Sistem ini mengambil data gempa dari USGS API dan berita dari RSS (Antara News + CNN Indonesia), memproses dengan Spark, dan menampilkan hasil di dashboard interaktif.

---

## 🚀 QUICK START - ALUR EKSEKUSI (April 2026 - UPDATED)

**Jalankan 5 terminal dalam urutan ini:**

| # | Terminal | Command | Tujuan |
|---|----------|---------|--------|
| 1️⃣ | Setup | `pip install -r requirements.txt` | Install dependencies |
| 2️⃣ | Docker | `docker compose -f docker-compose-hadoop.yml down && docker compose -f docker-compose-hadoop.yml up -d` | Start HDFS (restart untuk apply network fix) |
| 3️⃣ | Docker | `docker compose -f docker-compose-kafka.yml up -d` | Start Kafka |
| 4️⃣ | Producer API | `python kafka/producer_api.py` | Ambil data gempa dari USGS |
| 5️⃣ | Producer RSS | `python kafka/producer_rss.py` | Ambil berita dari Antara News + CNN |
| 6️⃣ | Consumer | `python kafka/consumer_to_hdfs.py` | Simpan Kafka data ke HDFS |
| 7️⃣ | Spark | `python spark/analysis.py` atau `$env:ALLOW_LOCAL_FALLBACK="1"; python spark/analysis.py` | Analisis data (tunggu 2-3 min setelah producers berjalan) |
| 8️⃣ | Dashboard | `python dashboard/app.py` | Buka web di http://localhost:8000 |

⏳ **Waktu:** ~2-3 menit dari setup sampai dashboard live

---

## 📋 DAFTAR ISI
1. [Prerequisite & Setup Awal](#-prerequisite--setup-awal)
2. [Menjalankan Docker Containers](#-menjalankan-docker-containers)
3. [Menjalankan Kafka Producers](#-menjalankan-kafka-producers)
4. [Menjalankan Consumer to HDFS](#-menjalankan-consumer-to-hdfs)
5. [Menjalankan Spark Analysis](#-menjalankan-spark-analysis)
6. [Menjalankan Flask Dashboard](#-menjalankan-flask-dashboard)
7. [Verifikasi Sistem](#-verifikasi-sistem)
8. [Troubleshooting](#-troubleshooting)

---

## 🔧 PREREQUISITE & SETUP AWAL

### 1.1 Pastikan Sudah Install:
- **Python 3.8+** - Download dari https://www.python.org/
- **Docker Desktop** - Download dari https://www.docker.com/products/docker-desktop/
- **Git** (opsional) - Untuk clone repository

### 1.2 Verifikasi Instalasi
```bash
python --version
docker --version
docker run hello-world
```

Pastikan semua tidak error ✅

### 1.3 Buka Command Prompt / PowerShell
Navigasi ke folder project:
```bash
cd d:\tes-bigdata-kafka
```

### 1.4 Setup Python Virtual Environment

⚠️ **PENTING:** Jika folder project pernah dipindah/di-rename, **hapus folder `venv` lama** terlebih dahulu!

```powershell
# Jika ada venv lama
Remove-Item -Recurse -Force venv
```

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

✅ **Indikator aktivasi:** Nama folder `(venv)` muncul di awal command prompt

**Verifikasi venv benar:**
```powershell
pip --version
# Harus menunjukkan path dengan "venv"
```

### 1.5 Install Python Dependencies
```bash
pip install -r requirements.txt
```

⚠️ **Pastikan berhasil!** Output harus:
```
Successfully installed kafka-python-ng-... requests-2.31.0 feedparser-6.0.11 flask-3.0.3 pyspark-3.5.1 numpy-...
```

Jika ada error `ModuleNotFoundError: No module named 'requests'`, jalankan ulang:
```bash
pip install -r requirements.txt
```

**Dependencies yang akan diinstall:**
- kafka-python-ng - Kafka producer/consumer
- requests==2.31.0 - HTTP requests untuk USGS API
- feedparser==6.0.11 - Parse RSS feed
- flask==3.0.3 - Web framework dashboard
- pyspark==3.5.1 - Apache Spark untuk analysis
- numpy>=1.26,<3 - Numerical computing
- python-dateutil==2.8.2 - Parse tanggal dari RSS feed (baru)

Tunggu sampai selesai dan tidak ada error ✅

### 1.6 Buat Docker Network (Wajib!)
```bash
docker network create hadoop_net
```

Ini adalah network yang akan digunakan oleh Kafka dan Hadoop untuk berkomunikasi.

---

## 🐳 MENJALANKAN DOCKER CONTAINERS

### 2.1 Jalankan Kafka + Zookeeper

**Buka Terminal/PowerShell BARU (tetap di folder project):**
```bash
docker compose -f docker-compose-kafka.yml up -d
```

**Output yang diharapkan:**
```
Creating zookeeper ... done
Creating kafka-broker ... done
```

⏳ **Tunggu 5-10 detik** sampai container fully running.

### 2.2 Jalankan Hadoop HDFS

**⚠️ PENTING (PERUBAHAN BARU - April 2026):**

Jika ini pertama kali menjalankan, atau Docker containers belum ter-restart setelah fix network:

```bash
# Hentikan container lama (jika ada)
docker compose -f docker-compose-hadoop.yml down

# Hapus volume lama supaya fresh start
docker volume prune -f

# Jalankan ulang dengan config baru
docker compose -f docker-compose-hadoop.yml up -d
```

**Atau jika sudah ter-restart sebelumnya:**
```bash
docker compose -f docker-compose-hadoop.yml up -d
```

**Output yang diharapkan:**
```
Creating hadoop-namenode ... done
Creating hadoop-datanode ... done
```

⏳ **Tunggu 30-60 detik** untuk NameNode initialize dan HDFS siap.

### 2.3 Verifikasi Semua Container Jalan
```bash
docker ps
```

**Pastikan ada 4 container:**
```
CONTAINER ID   IMAGE                    STATUS
xxxxx          bitnamilegacy/kafka      Up 1 minute
xxxxx          bitnamilegacy/zookeeper  Up 1 minute
xxxxx          apache/hadoop            Up 1 minute (namenode)
xxxxx          apache/hadoop            Up 1 minute (datanode)
```

Jika ada yang `Exited`, cek logs:
```bash
docker logs [CONTAINER_NAME]
```

✅ Semua container running? Lanjut ke TAHAP 3!

---

## 📤 MENJALANKAN KAFKA PRODUCERS

Producer adalah program yang mengambil data dari sumber eksternal dan mengirimnya ke Kafka topic.

### 3.1 Terminal 1 - Producer API (USGS Earthquake Data)

**Buka Terminal/PowerShell BARU:**
```bash
.\venv\Scripts\Activate.ps1
python kafka/producer_api.py
```

**Apa yang terjadi:**
- Mengambil data gempa dari USGS API
- Mengirim ke Kafka topic `gempa-api`
- Polling setiap 5 menit

**Output yang diharapkan:**
```
Producer API dimulai -> topic: gempa-api
Polling setiap 5 menit
==================================================

[14:23:45] Mengambil data USGS...
  [KIRIM] M5.2 | 87 km SE of Manado, Indonesia
  [KIRIM] M4.8 | 65 km NW of Banda Aceh, Indonesia
[14:23:47] berhasil memproses 2 gempa baru ke topic 'gempa-api'
Menunggu 5 menit...
```

✅ **Jangan tutup terminal ini!** Biarkan berjalan di background.

### 3.2 Terminal 2 - Producer RSS (News Articles)

**Buka Terminal/PowerShell BARU:**
```bash
.\venv\Scripts\Activate.ps1
python kafka/producer_rss.py
```

**Apa yang terjadi:**
- Mengambil artikel berita nasional dari RSS feed (Kompas, CNN Indonesia)
- Mengirim ke Kafka topic `gempa-rss`
- Polling setiap 5 menit
- **BARU:** Cache artikel di `.rss_cache.json` agar tidak double
- **BARU:** Ambil artikel dari 7 hari terakhir (bukan hanya real-time)
- **⚠️ PENTING:** Feed yang digunakan adalah berita nasional general (Kompas, CNN) — artikel gempa akan masuk ketika ada berita gempa yang di-publish di feed tersebut

**Output yang diharapkan (v2 - dengan improvements & updated feeds):**
```
Producer RSS dimulai -> topic: gempa-rss
Backfill: 7 hari terakhir
Polling interval: 300 detik (5 menit)

[14:24:10] Mengambil RSS feed...

  Feed: Berita Terkini - ANTARA News
     Artikel dalam feed: 50
     ✓ Gempa Berkekuatan 5.2 Guncang Sulawesi Tenggara
     ✓ BMKG Imbau Waspada Gempa Susulan

  Feed: CNN Indonesia | Berita Terkini Nasional
     Artikel dalam feed: 100
     ✓ Update Bencana Alam: Pantau Aktivitas Seismic
     ✓ Jaksa Agung Lantik 14 Kajati

[14:24:12] SUMMARY:
  Sent:          8 artikel baru
  Skipped cache: 42 artikel (sudah dikirim sebelumnya)
  Skipped old:   0 artikel (lebih lama dari 7 hari)
  Errors:        0
  Total cache:   50 URL

Menunggu 5 menit sebelum polling berikutnya...
```

**Notes:**
- ✅ **Updated Feeds (April 2026):** Menggunakan Antara News + CNN Indonesia (Kompas feed no longer available)
- ✅ **Persistent cache:** `.rss_cache.json` disimpan otomatis di folder project
- ✅ **Jangan hapus file `.rss_cache.json`** — ini menjaga duplikasi
- ✅ Untuk reset cache (debugging only): hapus file `.rss_cache.json` lalu restart producer
- ✅ Untuk ubah backfill: `$env:RSS_BACKFILL_DAYS="14"` sebelum run producer
- ℹ️ **Feed coverage:** Antara News (breaking news) + CNN Indonesia (national news). Artikel gempa akan masuk ketika ada berita gempa di-publish di kedua feed tersebut.

✅ **Jangan tutup terminal ini!** Biarkan berjalan di background.

---

## 📥 MENJALANKAN CONSUMER TO HDFS

Consumer membaca data dari Kafka topic dan menyimpannya ke HDFS (Hadoop Distributed File System).

### 4.1 Terminal 3 - Consumer to HDFS

**Buka Terminal/PowerShell BARU:**
```bash
.\venv\Scripts\Activate.ps1
python kafka/consumer_to_hdfs.py
```

**Apa yang terjadi:**
- Mendengarkan Kafka topics `gempa-api` dan `gempa-rss`
- Menyimpan batch data ke HDFS setiap 120 detik
- Membuat file lokal untuk live feed dashboard

**Output yang diharapkan:**
```
Direktori HDFS siap
Consumer berjalan -> membaca gempa-api dan gempa-rss

[14:24:30] API Buffer: 2 events
[14:24:30] RSS Buffer: 2 events
[Batch #1] API flushed
HDFS: /data/gempa/api/api_2026-04-29_14-24-30.json (2 records)
[Batch] RSS flushed
HDFS: /data/gempa/rss/rss_2026-04-29_14-24-30.json (2 records)
```

✅ **Jangan tutup terminal ini!** Biarkan berjalan di background.

### 4.2 Verifikasi Data Tersimpan di HDFS

**Buka Terminal/PowerShell BARU (atau di terminal sebelumnya, tapi data producer sudah jalan):**

**Tunggu minimal 2-3 menit** agar cukup data terkumpul.

Kemudian cek HDFS:
```bash
docker exec -it hadoop-namenode hdfs dfs -ls -R /data/gempa
```

**Output yang diharapkan:**
```
drwxr-xr-x   - root supergroup          0 2026-04-29 14:24 /data/gempa
drwxr-xr-x   - root supergroup          0 2026-04-29 14:24 /data/gempa/api
-rw-r--r--   1 root supergroup       2345 2026-04-29 14:24 /data/gempa/api/api_2026-04-29_14-24-30.json
drwxr-xr-x   - root supergroup          0 2026-04-29 14:24 /data/gempa/rss
-rw-r--r--   1 root supergroup       5678 2026-04-29 14:24 /data/gempa/rss/rss_2026-04-29_14-24-30.json
drwxr-xr-x   - root supergroup          0 2026-04-29 14:24 /data/gempa/hasil
```

✅ **Ada file JSON di `/data/gempa/api/` dan `/data/gempa/rss/`?** Bagus! Lanjut ke TAHAP 5.

Untuk lihat isi file:
```bash
docker exec -it hadoop-namenode hdfs dfs -cat /data/gempa/api/*.json | head -50
```

---

## 🔍 MENJALANKAN SPARK ANALYSIS

Spark akan membaca data dari HDFS, melakukan analisis, dan menghasilkan insights untuk dashboard.

### 5.0 ⚠️ PENTING - SAFE MODE HDFS

Setelah HDFS startup, sometimes it enters "safe mode" sambil waiting untuk data blocks replicate. Jika ini terjadi:

```bash
# Disable safe mode (jika HDFS stuck di safe mode ON)
docker exec hadoop-namenode hdfs dfsadmin -safemode leave

# Verify safe mode OFF
docker exec hadoop-namenode hdfs dfsadmin -safemode get
# Output harus: "Safe mode is OFF"
```

### 5.1 Terminal 4 - Spark Analysis

**Buka Terminal/PowerShell BARU:**
```bash
.\venv\Scripts\Activate.ps1
python spark/analysis.py
```

**⚠️ CATATAN PENTING (April 2026):**
Jika mendapat error `BlockMissingException: Could not obtain block` atau HDFS tidak bisa diakses:

**Opsi A - Gunakan Local Fallback (Recommended untuk testing pertama kali):**
```bash
.\venv\Scripts\Activate.ps1
$env:ALLOW_LOCAL_FALLBACK="1"
python spark/analysis.py
```
↑ Spark akan membaca dari file lokal `dashboard/data/live_api.json` jika HDFS tidak accessible.

**Opsi B - Tunggu HDFS data replication (Recommended untuk production):**
Pastikan producers sudah running cukup lama sehingga HDFS punya data:
1. Tunggu `producer_api.py` & `producer_rss.py` berjalan minimal **2-3 menit**
2. Tunggu `consumer_to_hdfs.py` menyimpan batch data ke HDFS
3. Baru jalankan Spark (tanpa ALLOW_LOCAL_FALLBACK)

**Apa yang terjadi:**
- Membaca data gempa dari HDFS `/data/gempa/api/`
- Melakukan 5 tipe analisis:
  1. **Distribusi Magnitudo** - Kategori gempa (Mikro, Minor, Sedang, Kuat)
  2. **Top 10 Wilayah Aktif** - Daftar wilayah dengan frekuensi gempa tertinggi
  3. **Distribusi Kedalaman** - Kategori kedalaman gempa (Dangkal, Menengah, Dalam)
  4. **Korelasi Magnitudo-Kedalaman** - Hubungan antara besaran dan kedalaman
  5. **Machine Learning** - RandomForest classifier untuk prediksi gempa kuat
- Menghasilkan file `dashboard/data/spark_results.json` untuk dashboard

**Output yang diharapkan:**
```
============================================================
GempaRadar - Apache Spark Analysis
============================================================
Data dari HDFS: 150 record

|-- id: string
|-- magnitude: double
|-- lokasi: string
...

+--------------------+------+--------+--------+
|kategori            |jumlah|avg_mag |max_mag |
+--------------------+------+--------+--------+
|Kuat (M>=5)         |45    |5.8     |7.2     |
|Sedang (M4-5)       |80    |4.5     |4.9     |
|Minor (M3-4)        |25    |3.2     |3.9     |
|Mikro (M<3)         |0     |null    |null    |
+--------------------+------+--------+--------+

+--------------------+------+--------+--------+
|wilayah             |jumlah|avg_mag |max_mag |
+--------------------+------+--------+--------+
|Sulawesi            |25    |5.5     |6.8     |
|Sumatera            |20    |5.2     |6.1     |
|Jawa                |15    |4.8     |5.3     |
...
+--------------------+------+--------+--------+

Hasil dashboard tersimpan di dashboard/data/spark_results.json
```

⏳ **Tunggu sampai selesai** (biasanya 30-60 detik), sampai output terakhir:
```
Hasil dashboard tersimpan di dashboard/data/spark_results.json
```

✅ Spark analysis selesai? Cek file hasil:
```bash
cat dashboard/data/spark_results.json
```

Atau gunakan Python untuk format yang lebih rapi:
```bash
python -m json.tool dashboard/data/spark_results.json
```

---

## 📊 MENJALANKAN FLASK DASHBOARD

Dashboard adalah web interface untuk visualisasi semua data dan analisis.

### 6.1 Terminal 5 - Flask Dashboard

**Buka Terminal/PowerShell BARU:**
```bash
.\venv\Scripts\Activate.ps1
python dashboard/app.py
```

**Apa yang terjadi:**
- Flask web server berjalan di port **8000** (bukan 5000)
- Membaca data dari:
  - `dashboard/data/spark_results.json` - Hasil analisis Spark
  - `dashboard/data/live_api.json` - Live earthquake data
  - `dashboard/data/live_rss.json` - Live news articles

⚠️ **Port sudah diubah ke 8000** untuk menghindari conflict dengan aplikasi lain.

**Output yang diharapkan:**
```
GempaRadar Dashboard -> http://localhost:8000
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://0.0.0.0:8000
 * WARNING in app.run(), this is a development server. Do not use it in production.
 * Press CTRL+C to quit.
```

✅ Dashboard sudah jalan!

### 6.2 Buka Dashboard di Browser

**Buka browser (Chrome, Firefox, Edge, Safari, dll) dan pergi ke:**
```
http://localhost:8000
```

**Apa yang akan dilihat di dashboard:**

1. **Distribusi Magnitudo** - Pie chart menunjukkan persentase gempa per kategori
2. **Top 10 Wilayah Paling Aktif** - Bar chart dengan wilayah yang paling sering gempa
3. **Distribusi Kedalaman** - Chart menunjukkan frekuensi gempa per kategori kedalaman
4. **Live Earthquake Feed** - Daftar 20 gempa terbaru dengan detail (magnitudo, lokasi, waktu)
5. **Live News Feed** - Daftar 10 artikel berita terbaru tentang gempa
6. **Machine Learning Result** - Akurasi RandomForest classifier untuk prediksi gempa kuat
7. **Historical Trends** - Tren aktivitas gempa per hari dan per jam

**Refresh page:** F5 atau Ctrl+R untuk melihat data terbaru

✅ **Sistem sudah berjalan sempurna!** 🎉

---

## ✅ VERIFIKASI SISTEM

Untuk memastikan semua komponen bekerja dengan baik, jalankan verifikasi berikut:

### 7.1 Verifikasi Kafka Topics
```bash
docker exec -it kafka-broker kafka-topics.sh --list --bootstrap-server localhost:9092
```

**Harus ada topics:**
```
gempa-api
gempa-rss
```

### 7.2 Verifikasi Kafka Consumer Group
```bash
docker exec -it kafka-broker kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group gemparadar-consumer
```

**Output menunjukkan:**
- Consumer group ID: `gemparadar-consumer`
- Topics: `gempa-api`, `gempa-rss`
- Lag: Jumlah pesan yang belum dikonsumsi

### 7.3 Verifikasi HDFS File System
```bash
docker exec -it hadoop-namenode hdfs dfs -ls -R /data/gempa
```

**Harus ada struktur:**
```
/data/gempa/
  /api/    <- Data dari USGS API
  /rss/    <- Data dari RSS feed
  /hasil/  <- Hasil analisis Spark
```

### 7.4 Verifikasi Spark Results File
```bash
ls -la dashboard/data/
```

**File yang harus ada:**
- `spark_results.json` - Hasil analisis Spark
- `live_api.json` - Live earthquake data (diupdate setiap 2 menit)
- `live_rss.json` - Live news data (diupdate setiap 2 menit)

### 7.5 Test Dashboard API Endpoints
```bash
# Lihat status file
curl http://localhost:5000/api/status

# Lihat live data
curl http://localhost:5000/api/live

# Lihat hasil analisis
curl http://localhost:5000/api/results
```

---

## 🔗 CHECKLIST - Pastikan Semua Ini Ada

- [ ] Python virtual environment aktif (ada `(venv)` di prompt)
- [ ] Dependencies terinstall (`pip list` menunjukkan kafka-python-ng, flask, pyspark, dll)
- [ ] Docker network `hadoop_net` sudah dibuat
- [ ] 4 containers jalan: zookeeper, kafka-broker, hadoop-namenode, hadoop-datanode
- [ ] Producer API berjalan dan mengirim data gempa
- [ ] Producer RSS berjalan dan mengirim artikel
- [ ] Consumer jalan dan menyimpan data ke HDFS
- [ ] File JSON ada di `/data/gempa/api/` dan `/data/gempa/rss/`
- [ ] Spark analysis berhasil dan membuat `spark_results.json`
- [ ] Dashboard berjalan di `http://localhost:8000`
- [ ] Data divisualisasikan di dashboard

---

## 📍 LOKASI FILE PENTING

```
d:\tes-bigdata-kafka\
├── kafka/
│   ├── producer_api.py          (USGS API producer)
│   ├── producer_rss.py          (RSS producer)
│   └── consumer_to_hdfs.py      (Consumer)
├── spark/
│   └── analysis.py              (Spark analysis)
├── dashboard/
│   ├── app.py                   (Flask app)
│   ├── data/
│   │   ├── spark_results.json   (Hasil analisis)
│   │   ├── live_api.json        (Live data API)
│   │   └── live_rss.json        (Live data RSS)
│   ├── templates/
│   │   └── index.html           (Frontend HTML)
│   └── static/
│       └── style.css            (Styling)
├── docker-compose-kafka.yml     (Kafka config)
├── docker-compose-hadoop.yml    (Hadoop config)
├── requirements.txt             (Python dependencies)
└── README.md                    (Dokumentasi awal)
```

---

## 🐛 TROUBLESHOOTING

### Problem: "ConnectionRefusedError: [Errno 111] Connection refused"

**Penyebab:** Kafka atau Hadoop container tidak jalan

**Solusi:**
```bash
docker ps
docker compose -f docker-compose-kafka.yml up -d
docker compose -f docker-compose-hadoop.yml up -d
```

---

### Problem: "docker: 'compose' is not a recognized command"

**Penyebab:** Docker version lama atau docker-compose belum terinstall

**Solusi:**
```bash
# Cek versi docker
docker --version

# Update Docker Desktop atau install docker-compose
# https://docs.docker.com/compose/install/
```

---

### Problem: "HDFS tidak bisa diakses: No such file or directory"

**Penyebab:** Container Hadoop belum fully initialize

**Solusi:**
```bash
# Tunggu 15-20 detik
docker logs hadoop-namenode

# Manual create direktori
docker exec -it hadoop-namenode hdfs dfs -mkdir -p /data/gempa/{api,rss,hasil}
```

---

### Problem: "Spark error: Could not find HDFS files"

**Penyebab:** Data belum terkumpul cukup di HDFS

**Solusi:**
```bash
# Tunggu 2-3 menit agar producer mengisi data
# Verifikasi dengan:
docker exec -it hadoop-namenode hdfs dfs -count /data/gempa/api

# Jika masih kosong, gunakan mode fallback lokal:
$env:ALLOW_LOCAL_FALLBACK="1"
python spark/analysis.py
```

---

### Problem: "Port 5000 is already in use"

**Penyebab:** Ada program lain menggunakan port 5000

**Solusi:**
```bash
# Opsi 1: Gunakan port lain
$env:PORT="5001"
python dashboard/app.py

# Kemudian buka http://localhost:5001

# Opsi 2: Matikan program yang pakai port 5000
# Cek dengan: netstat -ano | findstr :5000
```

---

### Problem: "Module 'pyspark' not found"

**Penyebab:** PySpark belum terinstall atau virtual env tidak aktif

**Solusi:**
```bash
# Pastikan venv aktif
.\venv\Scripts\Activate.ps1

# Reinstall pyspark
pip install pyspark==3.5.1
```

---

### Problem: "Consumer tidak membaca pesan dari Kafka"

**Penyebab:** Producer belum mengirim data atau topic belum dibuat

**Solusi:**
```bash
# Cek apakah producer API sudah berjalan
# (Lihat di terminal Producer API)

# Cek topics
docker exec -it kafka-broker kafka-topics.sh --list --bootstrap-server localhost:9092

# Jika kosong, topics akan auto-create saat producer mengirim data
# Tunggu 1 menit lalu coba lagi
```

---

## ⚠️ ISSUE YANG SUDAH DIHADAPI & SOLUSINYA

### Problem: "Unable to create process... venv\Scripts\python.exe not found"

**Penyebab:** Folder project dipindah/direname, tapi venv lama masih mereferensi path lama

**Solusi (WAJIB DILAKUKAN):**
```powershell
# 1. Hapus venv lama
Remove-Item -Recurse -Force venv

# 2. Buat venv baru di lokasi yang benar
python -m venv venv

# 3. Aktifkan venv
.\venv\Scripts\Activate.ps1

# 4. Install requirements
pip install -r requirements.txt
```

**Verifikasi berhasil:**
```powershell
pip --version
# Harus menunjukkan path dengan "venv"
```

---

### Problem: "ModuleNotFoundError: No module named 'requests'"

**Penyebab:** Dependencies belum terinstall atau venv tidak aktif

**Solusi:**
```powershell
# 1. Pastikan venv aktif (ada (venv) di prompt)
.\venv\Scripts\Activate.ps1

# 2. Verifikasi pip
pip --version

# 3. Install requirements lagi
pip install -r requirements.txt

# 4. Tunggu sampai sukses
# Output harus: Successfully installed kafka-python-ng-... requests-2.31.0 ...
```

---

### Problem: "An attempt was made to access a socket in a way forbidden by its access permissions"

**Penyebab:** Port 5000 sudah digunakan program lain atau firewall Windows memblokir

**Solusi (SUDAH DITERAPKAN):**
Port dashboard sudah diubah dari **5000 → 8000** di file `dashboard/app.py`.

Tinggal jalankan:
```powershell
python dashboard/app.py
```

Tidak perlu set `PORT` environment variable lagi. Dashboard akan otomatis berjalan di port **8000**.

Akses browser:
```
http://localhost:8000
```

---

## 🎯 MODE SIMULASI LOKAL (Optional - Tanpa Docker)

Jika Docker bermasalah, bisa simulasi sepenuhnya di lokal:

### Jalankan Producers dengan DRY_RUN
```bash
# Terminal 1
$env:DRY_RUN="1"
python kafka/producer_api.py

# Terminal 2
$env:DRY_RUN="1"
python kafka/producer_rss.py
```

### Jalankan Consumer dengan SIMULATE_HDFS
```bash
# Terminal 3
$env:SIMULATE_HDFS="1"
python kafka/consumer_to_hdfs.py
```

Data akan disimpan ke folder lokal `mock_hdfs/` instead of HDFS.

### Jalankan Spark dengan ALLOW_LOCAL_FALLBACK
```bash
# Terminal 4
$env:ALLOW_LOCAL_FALLBACK="1"
python spark/analysis.py
```

### Jalankan Dashboard seperti biasa
```bash
# Terminal 5
python dashboard/app.py
```

**Catatan:** Mode simulasi ini hanya untuk testing/debugging. Untuk grading/ETS, gunakan mode real dengan Docker dan HDFS.

---

## 📞 QUICK REFERENCE - Command Shortcuts

```bash
# ===== DOCKER =====
# Start all containers
docker compose -f docker-compose-kafka.yml up -d
docker compose -f docker-compose-hadoop.yml up -d

# Stop all containers
docker compose -f docker-compose-kafka.yml down
docker compose -f docker-compose-hadoop.yml down

# See container status
docker ps

# See container logs
docker logs kafka-broker
docker logs hadoop-namenode

# ===== KAFKA =====
# List topics
docker exec -it kafka-broker kafka-topics.sh --list --bootstrap-server localhost:9092

# Describe consumer group
docker exec -it kafka-broker kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group gemparadar-consumer

# ===== HDFS =====
# List files
docker exec -it hadoop-namenode hdfs dfs -ls -R /data/gempa

# Read file
docker exec -it hadoop-namenode hdfs dfs -cat /data/gempa/api/*.json

# Create directory
docker exec -it hadoop-namenode hdfs dfs -mkdir -p /data/gempa/api

# ===== PYTHON =====
# Activate venv (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Activate venv (Windows CMD)
venv\Scripts\activate.bat

# Activate venv (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run producer API
python kafka/producer_api.py

# Run producer RSS
python kafka/producer_rss.py

# Run consumer
python kafka/consumer_to_hdfs.py

# Run spark analysis
python spark/analysis.py

# Run dashboard
python dashboard/app.py

# ===== BROWSER =====
# Open dashboard (Port: 8000)
http://localhost:8000
```

---

## 🎓 ARSITEKTUR SISTEM

```
┌─────────────────────────────────────────────────────────────────┐
│                        GempaRadar System                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐         ┌──────────────┐                     │
│  │  USGS API    │         │ BMKG/Tempo   │                     │
│  │  Earthquake  │         │ RSS Feeds    │                     │
│  └──────┬───────┘         └──────┬───────┘                     │
│         │                        │                              │
│         └────────┬───────────────┘                             │
│                  │                                              │
│         ┌────────▼────────┐                                     │
│         │ Kafka Producers │                                     │
│         │ - API Producer  │                                     │
│         │ - RSS Producer  │                                     │
│         └────────┬────────┘                                     │
│                  │                                              │
│         ┌────────▼──────────────────┐                           │
│         │   Kafka Brokers & Topics  │                           │
│         │ - gempa-api               │                           │
│         │ - gempa-rss               │                           │
│         └────────┬──────────────────┘                           │
│                  │                                              │
│         ┌────────▼────────────────┐                             │
│         │ Consumer to HDFS        │                             │
│         │ (Buffer & Flush)        │                             │
│         └────────┬────────────────┘                             │
│                  │                                              │
│         ┌────────▼──────────────────────┐                       │
│         │   HDFS (Hadoop DFS)           │                       │
│         │ /data/gempa/api/   ← API      │                       │
│         │ /data/gempa/rss/   ← RSS      │                       │
│         │ /data/gempa/hasil/ ← Results  │                       │
│         └────────┬──────────────────────┘                       │
│                  │                                              │
│         ┌────────▼────────────────────┐                         │
│         │ Apache Spark Analysis       │                         │
│         │ 1. Magnitude Distribution   │                         │
│         │ 2. Top 10 Regions           │                         │
│         │ 3. Depth Distribution       │                         │
│         │ 4. Magnitude-Depth Corr.    │                         │
│         │ 5. ML RandomForest          │                         │
│         └────────┬────────────────────┘                         │
│                  │                                              │
│      ┌───────────┴──────────────┐                              │
│      │                          │                              │
│      ▼                          ▼                              │
│  Results JSON            Live Data JSON                       │
│  spark_results.json      live_api.json                        │
│                          live_rss.json                        │
│      │                          │                              │
│      └───────────┬──────────────┘                              │
│                  │                                              │
│         ┌────────▼──────────────────┐                           │
│         │   Flask Dashboard API     │                           │
│         │ - /api/results            │                           │
│         │ - /api/live               │                           │
│         │ - /api/status             │                           │
│         └────────┬──────────────────┘                           │
│                  │                                              │
│         ┌────────▼──────────────────┐                           │
│         │  Web Browser              │                           │
│         │ http://localhost:5000     │                           │
│         │ - Charts & Visualizations │                           │
│         │ - Live Data Feeds         │                           │
│         │ - ML Results              │                           │
│         └───────────────────────────┘                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎉 SELESAI!

Jika semua step di atas sudah diikuti dan berhasil, sistem **GempaRadar** sudah berjalan sepenuhnya dengan:

✅ Real-time data ingestion dari USGS API dan RSS feeds  
✅ Message streaming melalui Kafka  
✅ Distributed storage di Hadoop HDFS  
✅ Big data analysis dengan Apache Spark  
✅ Interactive dashboard dengan Flask & HTML/CSS  

Selamat! 🎊

---

**Pertanyaan atau masalah?** Baca bagian [Troubleshooting](#-troubleshooting) atau check logs di terminal masing-masing component.

**Happy analyzing earthquakes!** 🌍📊
