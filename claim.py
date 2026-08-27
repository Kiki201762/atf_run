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

API_ID =
API_HASH = ""
BOT_USERNAME = "ATF_AIRDROP_bot"
BASE_URL = "https://atfminers.asloni.online/miner/index.php"

# Auto claim mining:
# - CLAIM_INTERVAL_MINUTES: claim rutin tiap X menit (default 10 menit).
# - CLAIM_THRESHOLD: claim juga kalau pending_reward sudah capai angka ini.
# Set 0 untuk mematikan salah satunya (claim akhir sesi tetap jalan).
CLAIM_INTERVAL_MINUTES = 10
CLAIM_THRESHOLD = 0.5

# Lock global: serialisasi claim antar akun supaya tidak menembak server bersamaan.
# Server rate-limit per IP — claim serentak dari banyak akun memicu 429.
CLAIM_LOCK = asyncio.Lock()

# ۱. اولویت اول: خواندن از سکرت گیت‌هاب (برای سرور)
# ۲. اولویت دوم: خواندن از فایل محلی accounts.json (برای لپ‌تاپ و ترموکس)
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

async def claim_mining(session, acc_name, device_id, init_data, tg_id, claim_preview, rotator):
    """Claim hasil mining (tombol kuning). Return True kalau sukses.

    429 ditangani dengan backoff panjang (ikut Retry-After, atau 30-60s acak),
    bukan retry 2 detik yang malah memperparah rate limit.
    Network error -> rotasi proxy lalu retry.
    """
    payload = {
        "initData": init_data,
        "device_id": device_id,
        "request_id": str(uuid.uuid4()),
        "tg_id": tg_id,
        "claim_preview": claim_preview
    }
    for attempt in range(3):
        backoff = 2.0
        try:
            # Serialisasi antar akun + jitter, supaya claim tidak menumpuk di detik yang sama
            async with CLAIM_LOCK:
                await asyncio.sleep(random.uniform(0.5, 2.0))
                async with session.post(f"{BASE_URL}?action=claim&t={int(time.time()*1000)}", data=payload, proxy=rotator.current(), timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 429:
                        retry_after = resp.headers.get("Retry-After", "")
                        try:
                            backoff = max(float(retry_after), 30.0)
                        except ValueError:
                            backoff = random.uniform(30.0, 60.0)
                        print(f"[{acc_name}] Claim 429 (rate limited), attempt {attempt+1}. Backoff {backoff:.0f}s...")
                    else:
                        res = await resp.text()
                        if '"status":"success"' in res:
                            print(f"[{acc_name}] Mining claimed [SUCCESS] -> {res[:70]}")
                            return True
                        elif 'nothing to claim' in res.lower() or 'no pending' in res.lower():
                            print(f"[{acc_name}] Nothing to claim yet.")
                            return False
                        else:
                            print(f"[{acc_name}] Claim attempt {attempt+1} -> {res[:70]}")
        except Exception as ex:
            print(f"[{acc_name}] Claim network error (attempt {attempt+1}): {ex}")
            rotator.rotate()
        # Sleep di luar lock supaya akun lain tidak ikut terblokir
        await asyncio.sleep(backoff)
    return False

async def boost_worker(acc, start_delay=0.0):
    acc_name = acc.get("name", "Account")
    device_id = acc.get("device_id", "")
    rotator = acc.get("_rotator") or ProxyRotator([], acc_name)

    # اعمال تاخیر پله‌ای رندوم
    if start_delay > 0:
        await asyncio.sleep(start_delay)

    print(f"[{acc_name}] Proxy: {rotator._mask(rotator.current())}")

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        while True:
            try:
                init_data = await fetch_init_data(acc["session"])

                login_payload = {
                    "initData": init_data,
                    "device_id": device_id,
                    "request_id": str(uuid.uuid4())
                }

                # اضافه کردن تایم‌اوت برای جلوگیری از قفل شدن روی پاسخ سرور
                async with session.post(f"{BASE_URL}?action=login&t={int(time.time()*1000)}", data=login_payload, proxy=rotator.current(), timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    login_json = await resp.json(content_type=None)
                    if not login_json or login_json.get("status") != "success":
                        print(f"[{acc_name}] Login failed. Retrying in 10s...")
                        await asyncio.sleep(10)
                        continue

                    user_info = login_json.get("user", {})
                    tg_id = user_info.get("tg_id")
                    current_preview = float(user_info.get("pending_reward", 1.0))
                    print(f"[{acc_name}] Session Active | Synced Preview: {current_preview:.4f}")

                # Auto claim: sapu sisa pending dari run/sesi sebelumnya
                if current_preview >= 0.5:
                    print(f"[{acc_name}] Leftover pending {current_preview:.4f} detected, claiming...")
                    if await claim_mining(session, acc_name, device_id, init_data, tg_id, current_preview, rotator):
                        current_preview = 0.0

                session_start = time.time()
                last_break_time = time.time()
                last_claim_time = time.time()

                while time.time() - session_start < 2700:
                    current_preview += round(random.uniform(0.002, 0.008), 4)

                    boost_payload = {
                        "device_id": device_id,
                        "display_preview": f"{current_preview:.4f}",
                        "initData": init_data,
                        "request_id": str(uuid.uuid4()),
                        "tg_id": tg_id
                    }

                    async with session.post(f"{BASE_URL}?action=activate_boost&t={int(time.time()*1000)}", data=boost_payload, proxy=rotator.current(), timeout=aiohttp.ClientTimeout(total=15)) as b_resp:
                        if b_resp.status == 200:
                            try:
                                b_json = await b_resp.json(content_type=None)
                                if "pending_reward" in b_json:
                                    current_preview = float(b_json["pending_reward"])
                            except Exception:
                                pass
                            print(f"[{acc_name}] Tap Triggered -> Boost Active")
                        elif b_resp.status == 429:
                            retry_after = b_resp.headers.get("Retry-After", "")
                            try:
                                cool_down = max(float(retry_after), 15.0)
                            except ValueError:
                                cool_down = random.uniform(15.0, 30.0)
                            print(f"[{acc_name}] Boost 429 (rate limited). Cooling down {cool_down:.0f}s...")
                            await asyncio.sleep(cool_down)
                            continue
                        else:
                            print(f"[{acc_name}] Boost HTTP status: {b_resp.status}")

                    # Auto claim mid-session kalau pending sudah capai threshold
                    if CLAIM_THRESHOLD > 0 and current_preview >= CLAIM_THRESHOLD:
                        print(f"[{acc_name}] Pending {current_preview:.4f} hit threshold {CLAIM_THRESHOLD}, claiming...")
                        if await claim_mining(session, acc_name, device_id, init_data, tg_id, current_preview, rotator):
                            current_preview = 0.0
                            last_claim_time = time.time()

                    # Auto claim rutin tiap CLAIM_INTERVAL_MINUTES menit
                    elif CLAIM_INTERVAL_MINUTES > 0 and (time.time() - last_claim_time) >= CLAIM_INTERVAL_MINUTES * 60:
                        print(f"[{acc_name}] Interval claim ({CLAIM_INTERVAL_MINUTES} min), pending {current_preview:.4f}...")
                        if await claim_mining(session, acc_name, device_id, init_data, tg_id, current_preview, rotator):
                            current_preview = 0.0
                        last_claim_time = time.time()

                    current_time = time.time()

                    # وقفه کوتاه خستگی
                    next_break_interval = random.randint(900, 1200)
                    if current_time - last_break_time > next_break_interval:
                        micro_break = random.uniform(20.0, 40.0)
                        print(f"[{acc_name}] Human short break: resting for {micro_break:.1f}s...")
                        await asyncio.sleep(micro_break)
                        last_break_time = time.time()

                    # استراحت پایان سشن
                    elif (current_time - session_start) > random.randint(3600, 4800):
                        long_break = random.uniform(90.0, 120.0)
                        print(f"[{acc_name}] Session fatigue break: resting for {long_break:.1f}s...")
                        await asyncio.sleep(long_break)
                        session_start = time.time()
                        last_break_time = time.time()
                    else:
                        await asyncio.sleep(random.uniform(9.8, 10.6))

                # Auto claim di akhir sesi boost (~45 menit)
                print(f"[{acc_name}] Boost session ended. Claiming pending ({current_preview:.4f})...")
                if await claim_mining(session, acc_name, device_id, init_data, tg_id, current_preview, rotator):
                    current_preview = 0.0

            except Exception as e:
                print(f"[{acc_name}] Worker error: {e}. Rotating proxy & retrying in 5s...")
                rotator.rotate()
                await asyncio.sleep(5)

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

    print("==================================================")
    print(">>> ATF Boost Auto-Clicker (Optimized Delays)")
    print(f">>> Running {n_acc} Accounts Concurrently")
    if PROXIES:
        print(f">>> {len(PROXIES)} proxies loaded (2 per account: primary + backup)")
    else:
        print(">>> No proxies loaded — using DIRECT connection")
    print(">>> Press Ctrl + C to stop.")
    print("==================================================")

    tasks = []
    accumulated_delay = 0.0
    for idx, acc in enumerate(ACCOUNTS):
        if idx > 0:
            accumulated_delay += random.uniform(1.0, 2.0)
        tasks.append(boost_worker(acc, start_delay=accumulated_delay))

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOPPED] Auto-clicker stopped gracefully.")
