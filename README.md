# ATF Airdrop Bot — Auto Mining & Auto Task

Bot Telegram untuk game mining **@ATF_AIRDROP_bot** (ATF Miners, web app `atfminers.asloni.online`).
Bot ini meng-*claim* mining otomatis dan/atau menyelesaikan tugas-tugas (task) untuk banyak akun sekaligus.

> ⚠️ **Keamanan:** Jangan pernah commit `accounts.json`, `proxies.txt`, atau session string Telegram ke repository.
> File `.gitignore` disediakan untuk mencegah hal ini. Semua data sensitif dikirim lewat **GitHub Secrets**.

---

## Daftar Isi

- [1. Fitur](#1-fitur)
- [2. Kebutuhan (Prerequisites)](#2-kebutuhan-prerequisites)
- [3. Struktur File](#3-struktur-file)
- [4. Cara Jalankan di VPS (Ubuntu/Debian)](#4-cara-jalankan-lokal--vps-ubuntudebian)
  - [4a-V. Setup env (VPS)](#4a-v-setup-env-vps)
  - [4a-V. Buat session & accounts.json (VPS)](#4a-v-buat-session--isi-accountsjson-vps)
  - [4b-V. Jalankan bot di VPS (tmux)](#4b-v-jalankan-bot-di-vps-biar-tetap-jalan-walau-ssh-logout)
- [4-B. Cara Jalankan di Termux (Android/HP)](#4-b-cara-jalankan-di-termux-androidhp)
- [5. Cara Jalankan di GitHub Actions (Cloud / Otomatis 24 jam)](#5-cara-jalankan-di-github-actions-cloud--otomatis-24-jam)
  - [5a. Siapkan GitHub Secrets](#5a-siapkan-github-secrets)
  - [5b. Jalankan Manual / Otomatis (Cron)](#5b-jalankan-manual--otomatis-cron)

---

## 1. Fitur

- Multi-account: jalankan banyak akun Telegram sekaligus (paralel / concurrently).
- **Auto-claim mining**: claim otomatis dengan interval & threshold yang bisa diatur.
- **Auto-task**: kerjakan tugas (react latest, visit website, youtube like, twitter retweet, dll).
- **Proxy support**: tiap akun dapat 2 proxy (utama + cadangan), rotasi otomatis saat gagal.
- Bisa jalan di lokal (Termux/Laptop) **atau** di cloud via GitHub Actions.

Dua mode / varian script:

| File | Mode | Deskripsi |
|------|------|-----------|
| `tasks.py` | **Tasks** | Login → kerjakan task → claim mining. Cocok untuk bot airdrop yang butuh task. |
| `claim.py` | **Auto-clicker** | Fokus auto-claim mining rutin (tiap 10 menit default) + claim saat reward mencapai threshold. Tidak mengerjakan task. |

`session.py` — tool untuk membuat session string Telegram (sekali pakai, ingat session tersimpan otomatis).

---

## 2. Kebutuhan (Prerequisites)

- **Telegram API ID & API Hash** — buat di https://my.telegram.org → *API development tools*.
  - `API_ID` (angka) dan `API_HASH` (string).
- **Nomor telepon** dari akun-akun Telegram yang mau dipakai (untuk login dan dapat OTP).
- **Python 3.8+** (recommended 3.10).
- Library: `telethon`, `aiohttp`, `requests` (lihat `requirements.txt`).
- (Opsional) Daftar **proxy** berformat `user:pass@host:port`.

---

## 3. Struktur File

```
atf_run/
├── bot_runner_tasks.py        # Mode tasks
├── bot_runner_autoclicker.py  # Mode auto-claim / auto-clicker
├── generate_sessions.py       # Generator session string
├── requirements.txt           # Dependensi Python
├── accounts.json              # Data akun (JANGAN di-commit) — dikosongkan di repo
├── proxies.txt                # Daftar proxy (JANGAN di-commit)
├── .gitignore                 # Mencegah akun/proxy/env ikut ke git
└── .github/workflows/scheduler.yml  # Workflow GitHub Actions
```

---

## 4. Cara Jalankan Lokal — VPS (Ubuntu/Debian)


> ⚠️ **Bedakan dulu: ini untuk VPS (server Linux).** Kalau kamu pakai HP Android/Termux, lompat ke [bagian 4-B (Termux)](#4b-cara-jalankan-di-termux-android).

VPS = server Linux (biasanya Ubuntu/Debian) yang jalan 24 jam tanpa mati, jadi bot bisa claim terus menerus. Pakai `tmux`/`screen` supaya bot tetap jalan walau kamu logout dari SSH.

### 4a-V. Setup env (VPS)

```bash
git clone https://github.com/Kiki201762/atf_run
cd atf_run

# 1. Update sistem & install Python + venv + build tools (perlu utk install telethon)
sudo apt update
sudo apt install -y python3 python3-venv python3-pip build-essential

# 2. Buat virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependensi
pip install -r requirements.txt
```

### 4a-V. Buat session & isi accounts.json (VPS)

Gunakan `session.py`:

```bash
cd atf_run
source .venv/bin/activate
python session.py
```

> Isi setiap akun yang diminta: **Nama akun → Nomor telepon → OTP → (2FA bila aktif)**.
> `API_ID`/`API_HASH` dibaca otomatis dari env `TG_API_ID`/`TG_API_HASH`, atau file `TG_API_ID.txt`/`TG_API_HASH.txt` kalau ada — kalau tidak ada, akan diminta manual. Ketik `q` di prompt nama untuk selesai.

Setelah selesai, cek `accounts.json` (harus berisi akun-akunmu). Isi `proxies.txt` kalau pakai proxy (satu baris per proxy, `user:pass@host:port`, awalan `http://` ditambah otomatis).

### 4b-V. Jalankan bot di VPS (biar tetap jalan walau SSH logout)

Gunakan `tmux` supaya bot berjalan di background dan tidak mati saat kamu tutup SSH:

```bash
# Pertama masuk ke tmux
tmux new -s bot

# Di dalam tmux, jalankan bot (PILIH SALAH SATU mode):
source .venv/bin/activate
python task.py          # Mode tasks — ATAU
python claim.py    # Mode auto-claim mining

# Detach dari tmux (bot tetap jalan):     Ctrl+B lalu tekan D
# Lihat log/live lagi:                    tmux attach -t bot
# Hentikan bot dari dalam tmux:           Ctrl+C
# Cek semua tmux session:                 tmux ls
# Kill session bot:                       tmux kill-session -t bot
```

> Alternatif: pakai `screen` → `screen -S bot`, jalankan bot, detach dengan `Ctrl+A,D`, reattach `screen -r bot`.

---

## 4-B. Cara Jalankan di Termux (Android/HP)

Termux jalan di HP Android — dengan syarat perangkat tetap hidup & layar tidak terkunci penuh saat bot jalan (Atur agar tetap menyala, mis. screen timeout "never").

### 4a-T. Install Termux + Python & tools

```bash
# Update & upgrade
pkg update && pkg upgrade -y

# Install pendukung
pkg install -y python python-pip openssl git binutils build-essential
# build-essential/binutils kadang diperlukan utk install paket telethon/aiohttp
```

> Kalau instalasi telethon error karena masalah "binutils" / C library, jalankan: `pkg install -y build-essential binutils`.

### 4b-T. Clone & setup project di Termux

```bash
# Kalau belum install git:  pkg install -y git
git clone https://github.com/Kiki201762/atf_run
cd atf_run

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> Di Termux, `python` (bukan `python3`) yang tersedia. Path venv aktif: `.venv/bin/activate`.

### 4c-T. Buat session & isi accounts.json (Termux)

```bash
source .venv/bin/activate
python session.py
```

Isi: **Nama akun → Nomor telepon → OTP → (2FA bila aktif)**. Session otomatis tersimpan ke `accounts.json`.

### 4d-T. Jalankan bot di Termux

```bash
source .venv/bin/activate
python task.py          # Mode tasks — ATAU
python claim.py    # Mode auto-claim mining
```

> **PENTING Termux:** saat layar HP mati, proses sering di-hentikan Android (doze). Supaya bot jalan terus:
> 1. Aktifkan **wakelock** agar CPU tetap jalan: dalam Termux ketik `termux-wake-lock`.
> 2. Biarkan layar tetap menyala (atau set screen timeout panjang / "never") — tiap HP beda.
> 3. Jangan tutup aplikasi Termux (minimize saja), dan jangan "swipe-close" dari recent apps.
> 4. Kalau mau jalan di background tanpa app terbuka, pertimbangkan pakai Termux:Boot (screen/termux-services). Untuk pemakaian wajar, tetap buka Termux + wakelock adalah yang paling stabil.

> Untuk berhenti bot di Termux: tekan `Ctrl+C`. Kalau pakai `termux-wakelock`, akhiri dengan `termux-wake-unlock` setelah stop.

---

## 5. Cara Jalankan di GitHub Actions (Cloud / Otomatis 24 jam)

Cara ini membuat GitHub Actions menjalankan bot di server cloud (ubuntu-latest) tanpa laptop aktif, cocok untuk auto-claim 24/7. File workflow sudah disediakan di `.github/workflows/scheduler.yml`.

### 5a. Siapkan GitHub Secrets

1. Push repository ini ke GitHub.
2. Buka repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
3. Tambahkan secret berikut:

| Secret | Nilai | Contoh |
|--------|-------|--------|
| `ACCOUNTS_JSON` | Isi penuh `accounts.json` (daftar akun + session) dalam satu baris JSON | `[{"name":"Account 1","session":"1AZ...","device_id":"device-001"}]` |
| `TG_API_ID` | Telegram API ID (angka) | `33536389` |
| `TG_API_HASH` | Telegram API Hash | `916c...` |
| `PROXIES` *(opsional)* | Daftar proxy, satu baris per proxy (gunakan `\n` bila perlu) | `user:pass@host:port` |

> Penyimpanan session/acara via Secrets jauh lebih aman daripada menaruh di repo.

### 5b. Jalankan Manual / Otomatis (Cron)

Workflow dipicu oleh `workflow_dispatch` (manual) dan bisa diaktifkan cron internal GitHub.

**Cara 1 — Manual:**
1. Buka repository di GitHub → tab **Actions**.
2. Klik workflow **“ATF Bot Scheduler”** → **Run workflow** → **Run workflow**.

**Cara 2 — Otomatis via GitHub Cron (paling mudah):**
1. Edit `.github/workflows/scheduler.yml`.
2. Di bagian `on:`, hapus tanda komentar (`#`) pada blok `schedule`:

```yaml
on:
  schedule:
    - cron: '*/20 * * * *'   # Setiap 20 menit
  workflow_dispatch:
```

3. Commit & push. GitHub akan menjalankan bot sesuai jadwal.

**Cara 3 — Presisi via cron-job.org (opsional, akurat):**
1. Buka https://cron-job.org, buat akun, buat job baru.
2. *URL*: `https://api.github.com/repos/<USERNAME>/<REPO>/actions/workflows/scheduler.yml/dispatches`.
3. *Method*: `POST`. Tambahkan header `Authorization: Bearer <GITHUB_TOKEN>` (PA token with `workflow` scope) dan `Accept: application/vnd.github+json`.
4. Body: `{"ref":"main"}`. Set jadwal sesukanya.

---

## Catatan Teknis

- **Lock & serialisasi**: Server rate-limit per IP. `CLAIM_LOCK` menggerangkai request antar akun supaya tidak menembak server bersamaan (mengurangi status 429). Jangan jalankan terlalu banyak akun tanpa proxy.
- **Proxy rotasi**: tiap akun diberi 2 proxy (indeks `2*i` utama, `2*i+1` cadangan). Saat koneksi gagal, otomatis diputar ke cadangan.
- **Error 429 (rate limit)**: script sudah menangani dengan `Retry-After` / backoff acak.
- **Re-auth**: token/session di-re-auth secara berkala untuk menghindari kadaluarsa.

---

## Disclaimer

Gunakan dengan bijak dan patuhi ketentuan layanan platform (Telegram, ATF, dan layanan captcha). Penggunaan otomatisasi untuk airdrop/mining di luar ketentuan dapat berisiko pada akun Anda. Script ini disediakan apa adanya, tanpa jaminan.

## Lisensi

Tidak ditentukan (untuk penggunaan pribadi).
