import os
import json
import asyncio
import time
import uuid
import random
import urllib.parse
import aiohttp
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import RequestWebViewRequest

API_ID = 0  # (isi via env: TG_API_ID)
API_HASH = ""  # (isi via env: TG_API_HASH)
BOT_USERNAME = "ATF_AIRDROP_bot"
BASE_URL = "https://atfminers.asloni.online/miner/index.php"

# 1. Prioritas pertama: baca dari secret GitHub (untuk server)
# 2. Prioritas kedua: baca dari file lokal accounts.json (untuk laptop dan Termux)
RAW_ACCOUNTS = os.getenv("ACCOUNTS_JSON")
if RAW_ACCOUNTS:
    try:
        ACCOUNTS = json.loads(RAW_ACCOUNTS)
    except Exception as e:
        print(f"Error parsing ACCOUNTS_JSON from env: {e}")
        ACCOUNTS = []
elif os.path.exists("accounts.json"):
    try:
        with open("accounts.json", "r", encoding="utf-8") as f:
            ACCOUNTS = json.load(f)
    except Exception as e:
        print(f"Error reading local accounts.json: {e}")
        ACCOUNTS = []
else:
    ACCOUNTS = []

# ---- Proxy ----
# Sumber: env PROXIES (baris per proxy) ATAU file proxies.txt.
# Format per baris: user:pass@host:port  (awalan http:// ditambahkan otomatis).
# Tiap akun dapat 2 proxy: index 2*i = utama, 2*i+1 = cadangan. Rotasi otomatis
# kalau koneksi gagal. Kalau proxy kurang, dibagi round-robin; kalau kosong, direct.
def load_proxies():
    raw = os.getenv("PROXIES")
    lines = []
    if raw:
        lines = raw.splitlines()
    elif os.path.exists("proxies.txt"):
        try:
            with open("proxies.txt", "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            print(f"Error reading proxies.txt: {e}")
            lines = []
    proxies = []
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        if not ln.startswith("http://") and not ln.startswith("https://"):
            ln = "http://" + ln
        proxies.append(ln)
    return proxies

PROXIES = load_proxies()

class ProxyRotator:
    """Pegang daftar proxy satu akun (utama + cadangan) dan rotasi saat gagal."""
    def __init__(self, proxies, acc_name=""):
        self.proxies = proxies or []
        self.idx = 0
        self.acc_name = acc_name

    def current(self):
        if not self.proxies:
            return None
        return self.proxies[self.idx % len(self.proxies)]

    def rotate(self):
        if not self.proxies:
            return None
        self.idx = (self.idx + 1) % len(self.proxies)
        cur = self.current()
        print(f"[{self.acc_name}] Proxy rotate -> {self._mask(cur)}")
        return cur

    @staticmethod
    def _mask(url):
        if not url:
            return "DIRECT"
        try:
            hostport = url.split("@", 1)[1]
            return hostport
        except IndexError:
            return url

TASKS = [
    "telegram_react_latest",
    "website_visit",
    "youtube_like_comment",
    "twitter_retweet"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Origin": "https://atfminers.asloni.online",
    "Referer": "https://atfminers.asloni.online/miner/"
}

async def fetch_init_data(session_str):
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    bot_peer = await client.get_input_entity(BOT_USERNAME)
    
    web_view = await client(RequestWebViewRequest(
        peer=bot_peer,
        bot=bot_peer,
        platform="android",
        from_bot_menu=True,
        url="https://atfminers.asloni.online/miner/"
    ))
    await client.disconnect()
    
    parsed_url = urllib.parse.urlparse(web_view.url)
    params = urllib.parse.parse_qs(parsed_url.fragment)
    return params.get("tgWebAppData", [""])[0]

async def process_single_account(acc):
    initial_delay = random.uniform(0.5, 4.0)
    await asyncio.sleep(initial_delay)
    
    acc_name = acc.get("name", "Account")
    device_id = acc.get("device_id", "")
    rotator = acc.get("_rotator") or ProxyRotator([], acc_name)
    print(f"[{acc_name}] Initializing worker... | Proxy: {rotator._mask(rotator.current())}")

    try:
        await _process_account_inner(acc, acc_name, device_id, rotator)
    except Exception as e:
        print(f"[{acc_name}] ERROR (tidak berhenti, lanjut cycle berikutnya): {e}")


async def _process_account_inner(acc, acc_name, device_id, rotator):
    try:
        init_data = await fetch_init_data(acc["session"])
    except Exception as e:
        print(f"[{acc_name}] Telegram auth failed: {e}")
        return

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # 1. Login with safe retry (max 3 attempts)
        login_json = None
        for attempt in range(3):
            try:
                login_payload = {
                    "initData": init_data,
                    "device_id": device_id,
                    "request_id": str(uuid.uuid4())
                }
                async with session.post(f"{BASE_URL}?action=login&t={int(time.time()*1000)}", data=login_payload, proxy=rotator.current(), timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    login_json = await resp.json(content_type=None)
                    if login_json and login_json.get("status") == "success":
                        break
            except Exception as ex:
                rotator.rotate()
                if attempt == 2:
                    print(f"[{acc_name}] Login network error after 3 attempts: {ex}")
                    return
            await asyncio.sleep(2.0)

        if not login_json or login_json.get("status") != "success":
            print(f"[{acc_name}] Login rejected or failed.")
            return
            
        user_info = login_json.get("user", {})
        tg_id = user_info.get("tg_id")
        pending_mining = user_info.get("pending_reward", 0)
        print(f"[{acc_name}] Logged in | Pool: {user_info.get('mined_balance')} | Pending Mine: {pending_mining}")

        # 2. Trigger Tasks
        start_timestamps = {}
        shuffled_tasks = TASKS.copy()
        random.shuffle(shuffled_tasks)

        for task_id in shuffled_tasks:
            client_started_at = int(time.time())
            start_timestamps[task_id] = client_started_at
            
            payload = {
                "initData": init_data,
                "device_id": device_id,
                "request_id": str(uuid.uuid4()),
                "task_id": task_id,
                "tg_id": tg_id,
                "client_started_at": client_started_at
            }
            
            for attempt in range(3):
                try:
                    async with session.post(f"{BASE_URL}?action=start_task&t={int(time.time()*1000)}", data=payload, proxy=rotator.current(), timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            print(f"[{acc_name}] Started '{task_id}' [OK]")
                            break
                except Exception:
                    rotator.rotate()
                await asyncio.sleep(1.5)
            
            await asyncio.sleep(random.uniform(1.2, 2.5))

        # 3. Enhanced Dynamic Safe Wait Window
        processing_wait = random.uniform(38.0, 44.0)
        print(f"[{acc_name}] Waiting {processing_wait:.1f}s for timer verification...")
        await asyncio.sleep(processing_wait)

        # 4. Claim Tasks with Smart Cooldown Retries
        for task_id in shuffled_tasks:
            client_start = start_timestamps.get(task_id, int(time.time()) - 45)
            payload = {
                "initData": init_data,
                "device_id": device_id,
                "request_id": str(uuid.uuid4()),
                "task_id": task_id,
                "tg_id": tg_id,
                "client_started_at": client_start
            }
            
            for attempt in range(3):
                try:
                    async with session.post(f"{BASE_URL}?action=claim_task&t={int(time.time()*1000)}", data=payload, proxy=rotator.current(), timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        claim_res = await resp.text()
                        if '"status":"success"' in claim_res:
                            print(f"[{acc_name}] Claimed '{task_id}' [SUCCESS]")
                            break
                        elif 'Cooldown active' in claim_res:
                            if attempt < 2:
                                print(f"[{acc_name}] '{task_id}' Cooldown active. Waiting 15s for release...")
                                await asyncio.sleep(15.0)
                                continue
                            else:
                                print(f"[{acc_name}] Claimed '{task_id}' [COOLDOWN SKIPPED]")
                                break
                        elif 'already claimed' in claim_res.lower():
                            print(f"[{acc_name}] Task '{task_id}' was already claimed.")
                            break
                        elif attempt == 2:
                            print(f"[{acc_name}] Claimed '{task_id}' failed -> {claim_res[:50]}")
                except Exception as ex:
                    rotator.rotate()
                    if attempt == 2:
                        print(f"[{acc_name}] Network error on '{task_id}': {ex}")
                await asyncio.sleep(2.0)
            
            await asyncio.sleep(random.uniform(1.5, 2.5))

        # 5. Main Mining Claim (Yellow Button)
        await asyncio.sleep(random.uniform(2.0, 4.0))
        yellow_button_payload = {
            "initData": init_data,
            "device_id": device_id,
            "request_id": str(uuid.uuid4()),
            "tg_id": tg_id,
            "claim_preview": pending_mining
        }
        for attempt in range(3):
            try:
                async with session.post(f"{BASE_URL}?action=claim&t={int(time.time()*1000)}", data=yellow_button_payload, proxy=rotator.current(), timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    yellow_res = await resp.text()
                    print(f"[{acc_name}] Big Yellow Mine Claim -> {yellow_res[:70]}")
                    break
            except Exception:
                rotator.rotate()
                await asyncio.sleep(2.0)

    print(f"[{acc_name}] All actions completed.")

# ---- Scheduler ----
# Task di server reset tiap ~2 jam. Script ini TIDAK berhenti setelah satu
# putaran: ia menunggu sampai jadwal berikutnya lalu jalan lagi otomatis.
# RUN_INTERVAL_HOURS = jarak antar putaran (dalam jam).
# TASK_BUFFER_MINUTES = waktu tambahan untuk kelarin task sebelum run berikutnya.
RUN_INTERVAL_HOURS = 2.0
TASK_BUFFER_MINUTES = 5.0

async def main():
    if not ACCOUNTS:
        print("No accounts found in ACCOUNTS_JSON environment variable or accounts.json file.")
        return

    # Bagikan proxy: akun i dapat proxies[2*i] (utama) & proxies[2*i+1] (cadangan).
    # Kalau proxy tidak cukup, round-robin; kalau kosong, direct tanpa proxy.
    n_acc = len(ACCOUNTS)
    for idx, acc in enumerate(ACCOUNTS):
        acc_name = acc.get("name", f"Account {idx+1}")
        if PROXIES:
            if len(PROXIES) >= 2 * n_acc:
                pair = [PROXIES[2 * idx], PROXIES[2 * idx + 1]]
            else:
                pair = [PROXIES[idx % len(PROXIES)]]
                if len(PROXIES) > 1:
                    pair.append(PROXIES[(idx + 1) % len(PROXIES)])
            acc["_rotator"] = ProxyRotator(pair, acc_name)
        else:
            acc["_rotator"] = ProxyRotator([], acc_name)

    cycle = 0
    while True:
        cycle += 1
        cycle_start = time.time()

        print("==================================================")
        print(f">>> Cycle #{cycle} | Parallel Automation for {n_acc} Account(s)")
        if PROXIES:
            print(f">>> {len(PROXIES)} proxies loaded (2 per account: primary + backup)")
        else:
            print(">>> No proxies loaded — using DIRECT connection")
        print("==================================================")

        try:
            await asyncio.gather(*(process_single_account(acc) for acc in ACCOUNTS))
        except Exception as e:
            print(f">>> ERROR di cycle #{cycle}: {e}")
            print(">>> Loop tetap lanjut, tidak berhenti.")

        # Hitung sisa waktu tunggu supaya total ritme tetap ~2 jam per putaran,
        # ditambah buffer 5 menit supaya task di server sudah pasti reset.
        # Kalau satu putaran sendiri makan waktu > interval+buffer, tunggu minimal 60 detik.
        elapsed = time.time() - cycle_start
        total_interval = RUN_INTERVAL_HOURS * 3600 + TASK_BUFFER_MINUTES * 60
        wait_seconds = max(total_interval - elapsed, 60.0)
        next_run = time.strftime("%H:%M:%S", time.localtime(time.time() + wait_seconds))

        print("\n==================================================")
        print(f">>> Cycle #{cycle} selesai dalam {elapsed/60:.1f} menit.")
        print(f">>> Menunggu task reset (+{TASK_BUFFER_MINUTES:.0f} menit buffer). Run berikutnya jam {next_run} ({wait_seconds/60:.0f} menit lagi).")
        print(">>> Tekan Ctrl+C untuk berhenti.")
        print("==================================================")

        await asyncio.sleep(wait_seconds)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOPPED] Task runner berhenti.")
