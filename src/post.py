"""Kirim / update pesan daftar ke channel atau grup TANPA bot.py jalan.

Pemakaian:
    python src/post.py          # kirim pertama kali, setelahnya update pesan lama
    python src/post.py --new    # paksa kirim pesan baru
"""
import json
import sys
import urllib.error
import urllib.request

import common


def api(token, method, payload):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        return json.load(e)
    except (urllib.error.URLError, TimeoutError) as e:
        return {"ok": False, "description": f"koneksi gagal: {e}"}


def run(force_new=False):
    """Return pesan status. Raise RuntimeError kalau gagal."""
    cfg = common.load_config()
    chat = cfg.get("chat_id")
    thread_id = cfg.get("message_thread_id")

    if not chat:
        raise RuntimeError(
            'Isi "chat_id" di Config/config.json.'
        )

    if thread_id is not None:
        try:
            thread_id = int(thread_id)
            if thread_id < 1:
                raise ValueError
        except (TypeError, ValueError):
            raise RuntimeError(
                '"message_thread_id" harus berupa angka positif.'
            )
    data = common.load_bots()
    if not data["items"]:
        raise RuntimeError("Daftar masih kosong.")
    token = common.get_token()

    btns = [{"text": i["name"], "url": i["link"]} for i in data["items"]]
    msg = {
        "chat_id": chat,
        "text": data["title"],
        "reply_markup": {"inline_keyboard": common.chunk(btns, data["per_row"])},
    }

    if thread_id is not None:
        msg["message_thread_id"] = thread_id

    # Simpan status terpisah untuk setiap chat dan thread.
    state = common.read_json(common.STATE_FILE, {})
    state_key = f"{chat}/{thread_id}" if thread_id is not None else str(chat)
    mid = state.get(state_key)
    if mid and not force_new:
        r = api(token, "editMessageText", {**msg, "message_id": mid})
        if r.get("ok") or "not modified" in r.get("description", ""):
            return "Pesan lama di-update."

    r = api(token, "sendMessage", msg)
    if not r.get("ok"):
        raise RuntimeError(f"Gagal: {r.get('description')}")
    state[state_key] = r["result"]["message_id"]
    common.write_json(common.STATE_FILE, state)
    return "Terkirim. Pin pesannya biar selalu di atas."


if __name__ == "__main__":
    try:
        print(run(force_new="--new" in sys.argv))
    except RuntimeError as e:
        raise SystemExit(str(e))
