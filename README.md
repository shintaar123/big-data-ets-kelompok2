# GempaRadar - Big Data Earthquake Pipeline

## Deskripsi
GempaRadar adalah pipeline monitoring gempa bumi real-time untuk ETS Big Data topik 6. Sistem mengambil data gempa dari USGS dan berita dari RSS BMKG/Tempo, mengalirkannya melalui Kafka, menyimpannya ke HDFS, menganalisisnya dengan Spark, lalu menampilkannya di dashboard Flask.

## Arsitektur
`[USGS API + RSS] -> [Kafka Producers] -> [Topics gempa-api / gempa-rss] -> [Consumer to HDFS] -> [Spark Analysis] -> [Flask Dashboard]`

## Analisis Wajib
1. Distribusi magnitudo gempa.
2. Top 10 wilayah paling aktif.
3. Distribusi kedalaman gempa.

## Bonus yang Diimplementasikan
1. Alert Telegram untuk gempa signifikan.
2. Spark MLlib RandomForest untuk klasifikasi gempa kuat.
3. Dashboard chart dan peta interaktif.
4. Tren aktivitas harian dan per jam.

## Tim
- Zaenal Mustofa - setup Docker Hadoop dan Kafka
- Shinta Alya Ramadani - producer API USGS
- Salsa Bil Ulla - producer RSS dan consumer ke HDFS
- Angga Firmansyah - Spark analysis
- Hafiz Ramadhan - Flask dashboard
- *Solo Contributor: Perbaikan producer_rss.py (persistent cache + backfill)*

## Persiapan
1. Buat virtual environment dan install dependency:
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
2. Pastikan Docker Desktop aktif.
3. Buat Docker network yang dipakai dua compose file:
```powershell
docker network create hadoop_net
```

## Catatan Penting: RSS Feeds (Update)

**⚠️ PERHATIAN:** URL RSS BMKG dan Tempo yang asli sudah tidak valid (404). Telah diupdate ke feeds alternatif yang accessible.

**RSS Feeds yang digunakan:**
1. `https://rss.kompas.com/feed/kompas.com/megapolitan` — Berita nasional dari Kompas
2. `https://www.cnnindonesia.com/nasional/rss` — Berita nasional dari CNN Indonesia

**Catatan teknis:**
- Feed ini mencakup berita nasional (termasuk gempa ketika ada berita tentang gempa)
- Jika berita gempa jarang di-publish, harap sabar untuk pengumpulan data
- Untuk testing cepat: gunakan `DRY_RUN=1` mode untuk validate parsing tanpa menunggu Kafka

**Jika ingin mengganti feeds:**
Edit `kafka/producer_rss.py` line 22-25:
```python
RSS_FEEDS = [
    "https://your-feed-url-1",
    "https://your-feed-url-2",
]
```

Persyaratan feed:
- Harus valid RSS/Atom format
- Harus accessible (status 200, bukan 404)
- Harus punya field: `title`, `link`, `summary`, `published`

## Menjalankan Sistem End-to-End
1. Jalankan Kafka dan Hadoop:
```powershell
docker compose -f docker-compose-kafka.yml up -d
docker compose -f docker-compose-hadoop.yml up -d
```
2. Verifikasi container aktif:
```powershell
docker ps
```
3. Jalankan producer API:
```powershell
.\venv\Scripts\Activate.ps1
python kafka/producer_api.py
```
4. Jalankan producer RSS:
```powershell
.\venv\Scripts\Activate.ps1
python kafka/producer_rss.py
```
**Output yang diharapkan:**
```
Producer RSS dimulai -> topic: gempa-rss
Backfill: 7 hari terakhir
Polling interval: 300 detik (5 menit)

[16:30:00] Mengambil RSS feed...

  📰 Feed: BMKG Gempa Bumi
     Artikel dalam feed: 22
     ✓ Gempa M6.2 di Sulawesi Tenggara
     ✓ Aktivitas seismik meningkat di Lombok

  📰 Feed: Tempo - Gempa Bumi
     Artikel dalam feed: 15
     ✓ 2 Gempa Guncang Maluku Utara

[16:30:05] SUMMARY:
  Sent:          8 artikel baru
  Skipped cache: 29 artikel (sudah dikirim sebelumnya)
  Skipped old:   0 artikel (lebih lama dari 7 hari)
  Errors:        0
  Total cache:   37 URL

Menunggu 5 menit sebelum polling berikutnya...
```
5. Jalankan consumer ke HDFS:
```powershell
.\venv\Scripts\Activate.ps1
python kafka/consumer_to_hdfs.py
```
6. Tunggu minimal 2 menit lalu cek HDFS:
```powershell
docker exec -it hadoop-namenode hdfs dfs -ls -R /data/gempa
```
7. Jalankan Spark:
```powershell
.\venv\Scripts\Activate.ps1
python spark/analysis.py
```
8. Jalankan dashboard:
```powershell
.\venv\Scripts\Activate.ps1
python dashboard/app.py
```
9. Buka `http://localhost:5000`.

## Verifikasi ETS
1. List Kafka topic:
```powershell
docker exec -it kafka-broker kafka-topics.sh --list --bootstrap-server localhost:9092
```
2. Cek consumer group:
```powershell
docker exec -it kafka-broker kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group gemparadar-consumer
```
3. Cek HDFS:
```powershell
docker exec -it hadoop-namenode hdfs dfs -ls -R /data/gempa
```

## Mode Simulasi Lokal
Mode ini hanya untuk pengujian saat Docker/HDFS belum aktif.
1. Validasi producer tanpa Kafka:
```powershell
$env:DRY_RUN="1"
python kafka/producer_api.py
python kafka/producer_rss.py
```
2. Simulasi target HDFS ke folder lokal `mock_hdfs`:
```powershell
$env:SIMULATE_HDFS="1"
python kafka/consumer_to_hdfs.py
```
3. Jalankan Spark dengan fallback data lokal:
```powershell
$env:ALLOW_LOCAL_FALLBACK="1"
python spark/analysis.py
```

## Catatan
1. Dashboard membaca `dashboard/data/spark_results.json`, `live_api.json`, dan `live_rss.json`.
2. Spark secara default wajib membaca dari HDFS. Fallback lokal hanya dipakai untuk simulasi, bukan mode penilaian utama ETS.
3. **Producer RSS** sekarang menggunakan persistent cache file `.rss_cache.json` — artikel lama tidak akan di-kirim ulang bahkan setelah restart
4. **Backfill support** pada producer RSS memungkinkan pengambilan artikel dari 7 hari terakhir dengan `$env:RSS_BACKFILL_DAYS=N`
