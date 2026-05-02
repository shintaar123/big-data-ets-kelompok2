# GempaRadar — Panduan Setup UPDATED (Windows)

> Versi ini sudah memperhitungkan semua bug yang ditemukan saat setup di Windows. Ikuti urutan ini persis!

---

## 🔧 RINGKASAN FILE YANG DIUBAH

| File                          | Masalah Asli                                                                                                 | Yang Difix                                                                                      |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| `docker-compose-hadoop.yml` | Volume path `/tmp/...` bermasalah di Windows, NameNode crash karena permission                             | Path diganti ke `/hadoop/dfs/name`, jalankan sebagai `root`, auto-format HDFS sebelum start |
| `hadoop.env`                | Tidak ada config yang kasih tahu Hadoop simpan data di mana                                                  | Tambah `HDFS-SITE.XML_dfs.namenode.name.dir=/hadoop/dfs/name`                                 |
| `kafka/consumer_to_hdfs.py` | `for message in consumer` pakai `select()` Unix yang crash di Windows → `Invalid file descriptor: -1` | Ganti ke `consumer.poll(timeout_ms=3000)` + tambah `socket_options=[]`                      |
| `spark/analysis.py`         | Java 21 tidak kompatibel dengan PySpark 3.5 → error `getSubject is not supported`                         | Tidak ubah kode — solusinya install**Java 11** dan set `JAVA_HOME` manual              |
| `spark/analysis.py`         | Python 3.12+ menghapus modul `distutils` → `bonus_ml` error di dashboard                                | Tambah patch `setuptools` di baris paling atas `analysis.py`                                |

---

## ✅ PREREQUISITE TAMBAHAN (Wajib untuk Windows)

### Install Java 11 (WAJIB — Java 21+ tidak kompatibel PySpark 3.5)

```powershell
winget install Microsoft.OpenJDK.11
```

Setelah install, **jangan tutup PowerShell** — PATH belum update otomatis. Set manual:

```powershell
$env:JAVA_HOME = "C:\Program Files\Microsoft\jdk-11.0.30.7-hotspot"
$env:PATH = "$env:JAVA_HOME\bin;" + $env:PATH

# Verifikasi — harus muncul "11.x.x"
java -version
```

> ⚠️ Set ini harus diulang **setiap kali buka terminal baru** sebelum jalankan Spark.
> Untuk permanen: tambahkan ke System Environment Variables di Windows.

### Fix distutils (WAJIB — Python 3.12+ tidak punya distutils bawaan)

```powershell
pip install setuptools --upgrade
```

---

## 🚀 ALUR EKSEKUSI LENGKAP

### Persiapan Awal (Sekali Saja)

```powershell
# 1. Buat virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt
pip install setuptools --upgrade

# 3. Buat Docker network
docker network create hadoop_net
```

---

### TAHAP 1 — Start Docker Containers

**Buka PowerShell baru, aktifkan venv:**

```powershell
.\venv\Scripts\Activate.ps1
```

**Jalankan Kafka dulu:**

```powershell
docker compose -f docker-compose-kafka.yml up -d
```

**Bersihkan Hadoop lama (penting!), lalu start ulang:**

```powershell
docker compose -f docker-compose-hadoop.yml down -v --remove-orphans
docker compose -f docker-compose-hadoop.yml up -d
```

**Tunggu ~20 detik, lalu verifikasi — harus ada 4 container UP:**

```powershell
docker ps
```

Output yang benar:

```
hadoop-datanode   Up
hadoop-namenode   Up
kafka-broker      Up
zookeeper         Up
```

**Buat folder di HDFS:**

```powershell
docker exec -it hadoop-namenode hdfs dfs -mkdir -p /data/gempa/api
docker exec -it hadoop-namenode hdfs dfs -mkdir -p /data/gempa/rss
docker exec -it hadoop-namenode hdfs dfs -mkdir -p /data/gempa/hasil

# Verifikasi
docker exec -it hadoop-namenode hdfs dfs -ls -R /data/gempa
```

---

### TAHAP 2 — Terminal A: Producer API

**Buka PowerShell baru:**

```powershell
.\venv\Scripts\Activate.ps1
python kafka/producer_api.py
```

Output normal:

```
Producer API dimulai -> topic: gempa-api
[08:46:25] Mengambil data USGS...
  [KIRIM] M4.3 | 51 km NE of Manokwari, Indonesia
  ...
berhasil memproses 20 gempa baru
Menunggu 5 menit...
```

> Biarkan terminal ini tetap berjalan.

---

### TAHAP 3 — Terminal B: Producer RSS

**Buka PowerShell baru:**

```powershell
.\venv\Scripts\Activate.ps1
python kafka/producer_rss.py
```

Output normal:

```
Producer RSS dimulai -> topic: gempa-rss
Backfill: 7 hari terakhir
[KIRIM] Prabowo Hadiri...
...
```

> Biarkan terminal ini tetap berjalan.

---

### TAHAP 4 — Terminal C: Consumer to HDFS

**Buka PowerShell baru:**

```powershell
.\venv\Scripts\Activate.ps1
python kafka/consumer_to_hdfs.py
```

Output normal (setelah fix):

```
Direktori HDFS siap
Consumer berjalan -> membaca gempa-api dan gempa-rss
[INFO] Kafka consumer terhubung, mulai polling...
  [API] 51 km NE of Manokwari, Indonesia
  ...
HDFS: /data/gempa/api/api_2026-05-01_09-06-41.json (20 records)
[Batch #1] API flushed
```

> Jika muncul `[WARN] Consumer error: Invalid file descriptor: -1` → pastikan file `consumer_to_hdfs.py` sudah diupdate ke versi yang pakai `consumer.poll()`.

**Tunggu minimal 2 menit** sampai ada output `[Batch #1] API flushed`, baru lanjut ke Spark.

**Verifikasi HDFS terisi:**

```powershell
docker exec -it hadoop-namenode hdfs dfs -ls -R /data/gempa
```

Harus ada file `.json` di `/data/gempa/api/` dan `/data/gempa/rss/`.

---

### TAHAP 5 — Terminal D: Spark Analysis

**⚠️ Set Java 11 dulu di terminal ini sebelum apapun:**

```powershell
$env:JAVA_HOME = "C:\Program Files\Microsoft\jdk-11.0.30.7-hotspot"
$env:PATH = "$env:JAVA_HOME\bin;" + $env:PATH
$env:PYSPARK_PYTHON = (Get-Command python).Source
$env:PYSPARK_DRIVER_PYTHON = (Get-Command python).Source
$env:ALLOW_LOCAL_FALLBACK = "1"

.\venv\Scripts\Activate.ps1
python spark/analysis.py
```

> Copy semua baris di atas sekaligus, paste ke terminal, Enter.

Output normal (ada WARNING soal BlockMissingException — itu normal, bukan error fatal):

```
============================================================
GempaRadar - Apache Spark Analysis
============================================================
Data dari HDFS: 20 record
...
HDFS bridge OK: /data/gempa/hasil/mag_dist/mag_dist.json
HDFS bridge OK: /data/gempa/hasil/wilayah/wilayah.json
...
Hasil dashboard tersimpan di dashboard/data/spark_results.json
--- RINGKASAN ---
Total gempa    : 20
Avg magnitude  : 4.57
Max magnitude  : 5.5
ML accuracy    : 0.75
```

---

### TAHAP 6 — Terminal E: Dashboard

**Buka PowerShell baru:**

```powershell
.\venv\Scripts\Activate.ps1
python dashboard/app.py
```

Buka browser ke: **http://localhost:5000**

> Setelah browser terbuka, tekan **Ctrl+Shift+R** (hard refresh) supaya CSS dan data terbaru ter-load.

---

## 🔄 RESET KAFKA OFFSET (Jika Consumer Tidak Baca Data API)

Kalau consumer sudah sempat crash sebelum fix, offset Kafka sudah ter-commit → consumer baru tidak baca ulang. Solusinya:

```powershell
# Stop consumer dulu (Ctrl+C)

# Reset offset ke paling awal
docker exec -it kafka-broker kafka-consumer-groups.sh `
  --bootstrap-server localhost:9092 `
  --group gemparadar-consumer `
  --topic gempa-api `
  --reset-offsets `
  --to-earliest `
  --execute

# Jalankan consumer lagi
python kafka/consumer_to_hdfs.py
```

---

## 🐛 TROUBLESHOOTING CEPAT

| Gejala                                         | Penyebab                                      | Solusi                                                                             |
| ---------------------------------------------- | --------------------------------------------- | ---------------------------------------------------------------------------------- |
| `container is not running` di NameNode       | NameNode crash saat format                    | Pakai `docker-compose-hadoop.yml` versi baru (user: root + auto-format)          |
| `Invalid file descriptor: -1` di consumer    | Bug Windows + kafka-python iterasi langsung   | Pakai `consumer_to_hdfs.py` versi baru (pakai `.poll()`)                       |
| `getSubject is not supported` di Spark       | Java 21 tidak kompatibel PySpark 3.5          | Set `$env:JAVA_HOME` ke Java 11 sebelum run                                      |
| `Missing Python executable` di Spark         | Path dengan spasi di Windows                  | Set `$env:PYSPARK_PYTHON = (Get-Command python).Source`                          |
| `BlockMissingException` di Spark             | Spark coba akses datanode IP internal Docker  | Normal —`ALLOW_LOCAL_FALLBACK=1` sudah handle ini                               |
| `/data/gempa/api` kosong di HDFS             | Consumer crash lama sudah commit offset       | Reset Kafka offset (lihat section di atas)                                         |
| `bonus_ml` error / tidak muncul di dashboard | Python 3.12+ tidak punya `distutils` bawaan | `pip install setuptools --upgrade` + tambah patch import di atas `analysis.py` |

---

## 📋 CHECKLIST AKHIR

- [ ] 4 container Docker jalan: zookeeper, kafka-broker, hadoop-namenode, hadoop-datanode
- [ ] Producer API berjalan dan kirim data USGS
- [ ] Producer RSS berjalan dan kirim berita
- [ ] Consumer menampilkan `[Batch #1] API flushed` dan `RSS flushed`
- [ ] `hdfs dfs -ls -R /data/gempa` menunjukkan file `.json` di `/api/` dan `/rss/`
- [ ] Spark analysis selesai dengan output `Hasil dashboard tersimpan di spark_results.json`
- [ ] Dashboard terbuka di `http://localhost:8000` dengan data visualisasi
- [ ] Panel **Predictive Model (MLlib)** menampilkan data (bukan error)

---

*Dibuat berdasarkan sesi debug live — semua fix sudah diverifikasi berjalan di Windows dengan Docker Desktop.*
