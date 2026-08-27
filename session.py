"""
Generate session string untuk ATF miner multi-account (pola mb-bot/session.py).
Tiap akun: input API_ID -> API_HASH -> Phone -> OTP -> auto-save ke accounts.json
dengan device_id otomatis. Loop terus sampai ketik 'q'.

Bedanya dari sesi.py lama: hasil langsung tersimpan (nggak perlu copy manual),
jadi nggak perlu dijalankan ulang berulang-ulang.
"""
import os
import json
import uuid
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

# Prioritas API credentials: env -> file txt -> prompt terminal (mirip sesi.py lama)
API_ID = int(os.getenv("TG_API_ID", 0) or 0)
API_HASH = os.getenv("TG_API_HASH", "")

if not API_ID and os.path.exists("TG_API_ID.txt"):
    try:
        with open("TG_API_ID.txt", "r", encoding="utf-8") as f:
            val = f.read().strip()
            if val.isdigit():
                API_ID = int(val)
    except Exception:
        pass

if not API_HASH and os.path.exists("TG_API_HASH.txt"):
    try:
        with open("TG_API_HASH.txt", "r", encoding="utf-8") as f:
            API_HASH = f.read().strip()
    except Exception:
        pass


def load_accounts():
    if os.path.exists("accounts.json"):
        try:
            with open("accounts.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_accounts(accounts):
    with open("accounts.json", "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)


def generate_device_id(existing_ids):
    """Bikin device_id unik yang belum dipakai (mis. device-007)."""
    used = set(existing_ids)
    n = 1
    while f"device-{n:03d}" in used:
        n += 1
    return f"device-{n:03d}"


async def generate_one(accounts):
    """Generate 1 akun: API_ID -> API_HASH -> Phone -> OTP -> save."""
    idx = len(accounts) + 1
    print(f"\n{'='*50}")
    print(f"  ACCOUNT #{idx}")
    print(f"{'='*50}")

    # Nama akun
    acc_name = input(f"[{idx}] Nama akun (atau 'q' untuk selesai): ").strip()
    if acc_name.lower() == "q":
        return False
    if not acc_name:
        print("[SKIP] Nama kosong, coba lagi.")
        return True

    # Cek duplikat
    for acc in accounts:
        if acc.get("name") == acc_name:
            print(f"[WARN] '{acc_name}' sudah ada. Pakai nama lain.")
            return True

    # Ambil API_ID / API_HASH (env/file) kalau belum ketemu, baru prompt
    api_id = API_ID
    api_hash = API_HASH
    if not api_id:
        input_id = input(f"[{idx}] API_ID: ").strip()
        if not input_id.isdigit():
            print("[SKIP] API_ID tidak valid, coba lagi.")
            return True
        api_id = int(input_id)
    if not api_hash:
        api_hash = input(f"[{idx}] API_HASH: ").strip()
        if not api_hash:
            print("[SKIP] API_HASH kosong, coba lagi.")
            return True

    # Login Telegram
    print(f"\n--- Connecting to Telegram untuk '{acc_name}' ---")
    client = TelegramClient(StringSession(), api_id, api_hash)
    try:
        await client.connect()

        phone = input(f"[{idx}] Nomor telepon (format +62xxx): ").strip()
        await client.send_code_request(phone)

        code = input(f"[{idx}] OTP code: ").strip()
        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            password = input(f"[{idx}] 2FA Password: ").strip()
            await client.sign_in(phone=phone, password=password)

        me = await client.get_me()
        session_str = client.session.save()

        print(f"✅ Logged in: {me.first_name} (@{me.username})")

        # Simpan otomatis + device_id unik biar langsung bisa dipakai task.py/run.py
        accounts.append({
            "name": acc_name,
            "session": session_str,
            "device_id": generate_device_id(acc.get("device_id", "") for acc in accounts),
        })
        save_accounts(accounts)
        print(f"[OK] Saved! accounts.json sekarang punya {len(accounts)} account(s)")
    except Exception as e:
        print(f"[ERROR] Gagal: {e}")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

    return True


async def main():
    if not API_ID and not os.path.exists("TG_API_ID.txt"):
        print("[INFO] API_ID/API_HASH tidak ketemu di env/ file. Akan diminta per akun.")
    accounts = load_accounts()
    print(f"[INFO] Loaded {len(accounts)} existing account(s) dari accounts.json")
    print("=== Generate Session (loop mode) ===")
    print("Tiap akun: Phone -> OTP -> auto-save ke accounts.json")
    print("Ketik 'q' di prompt nama untuk selesai\n")

    while True:
        cont = await generate_one(accounts)
        if not cont:
            break

    print(f"\n[DONE] Total {len(accounts)} account(s) di accounts.json")


if __name__ == "__main__":
    asyncio.run(main())
