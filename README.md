# 🌋 GempaRadar - Big Data Earthquake Pipeline (ETS)

## 📜 Deskripsi
Sistem monitoring gempa bumi real-time yang mengimplementasikan arsitektur Data Lakehouse modern dengan Apache Kafka, HDFS, Apache Spark, dan Flask Dashboard.

## 🏗️ Arsitektur
`[USGS API/RSS] → [Kafka Producer] → [Kafka Topics] → [Consumer to HDFS] → [Spark Analysis] → [Flask Dashboard]`

## ✨ Fitur
### ✅ Analisis Wajib
1. **Statistik Gempa**: Distribusi magnitude, trend harian, top 10 lokasi
2. **Bahaya Seismik**: Alert level, potensi tsunami, gempa signifikan (≥M5.5)
3. **Pola Temporal-Spasial**: Distribusi per jam, hotspot koordinat

### 🎁 Bonus (+10 Poin)
1. 📩 **Real-time Alert**: Notifikasi Telegram otomatis untuk gempa ≥M6.0
2. 🤖 **Predictive Model**: Spark MLlib (RandomForest) prediktor gempa signifikan
3. 🗺️ **Interactive Map**: Leaflet.js dengan marker dinamis berdasarkan magnitude
4. 📅 **Historical Comparison**: Perbandingan data hari ini vs 30 hari terakhir
5. 📱 **Mobile Responsive**: Dashboard adaptif untuk semua ukuran layar

## 🛠️ Cara Menjalankan

### ─── PERSIAPAN AWAL (Sekali Saja) ─────────
Buka terminal baru di folder proyek, lalu buat virtual environment:
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### ─── STEP 1: Hadoop (Anggota 1) ─────────
Buka terminal dan jalankan container Hadoop:
```powershell
docker network create hadoop_net
docker compose -f docker-compose-hadoop.yml up -d
# Tunggu 30 detik
docker exec hadoop-namenode hdfs dfs -mkdir -p /data/gempa/api
docker exec hadoop-namenode hdfs dfs -mkdir -p /data/gempa/rss
docker exec hadoop-namenode hdfs dfs -mkdir -p /data/gempa/hasil
docker exec hadoop-namenode hdfs dfs -chmod -R 777 /data
```

### ─── STEP 2: Kafka (Anggota 1) ─────────
Jalankan container Kafka:
```powershell
docker compose -f docker-compose-kafka.yml up -d
# Tunggu 20 detik, lalu verifikasi:
docker exec kafka-broker kafka-topics.sh --list --bootstrap-server localhost:9092
```

### ─── STEP 3: Producer API (Anggota 2) ─────────
Buka **Terminal Baru**, lalu jalankan:
```powershell
.\venv\Scripts\Activate.ps1
python kafka/producer_api.py
```

### ─── STEP 4: Producer RSS (Anggota 3) ─────────
Buka **Terminal Baru**, lalu jalankan:
```powershell
.\venv\Scripts\Activate.ps1
python kafka/producer_rss.py
```

### ─── STEP 5: Consumer ke HDFS (Anggota 3) ─────────
Buka **Terminal Baru**, lalu jalankan:
```powershell
.\venv\Scripts\Activate.ps1
python kafka/consumer_to_hdfs.py
```
*(Tunggu 2 menit sampai muncul pesan `[Batch #1] API flushed ✅`)*

### ─── STEP 6: Spark Analysis (Anggota 4) ─────────
Buka **Terminal Baru**, lalu jalankan:
```powershell
.\venv\Scripts\Activate.ps1
python spark/spark_analysis.py
```

### ─── STEP 7: Dashboard (Anggota 5) ─────────
Buka **Terminal Baru**, lalu jalankan:
```powershell
.\venv\Scripts\Activate.ps1
python dashboard/app.py
```
*(Buka browser → http://localhost:5000)*

## 👥 Tim Kelompok
- Zaenal Mustofa - 50272410
- Shinta Alya Ramadani - 5027241016
- Salsa Bil Ulla - 5027241
- Angga Firmansyah - 5027241062
- Hafiz Ramadhan - 50272410