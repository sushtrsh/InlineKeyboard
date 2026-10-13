"""Helper bersama bot.py & manage.py (tanpa dependensi telegram)."""
import copy
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "Config" / "config.json"
TOKEN_PLACEHOLDER = "ISI_TOKEN_DARI_BOTFATHER"

# command bawaan, nggak boleh dipakai buat command buatan
RESERVED = {"start", "help", "id", "admin", "inlinekeyboard", "edit",
            "addcmd", "delcmd", "post", "batal"}

DEFAULT = {
    "token": "",
    "admin_ids": [],
    "chat_id": "",  # tujuan default /post dan manage.py post
    "start_text": "Halo <b>{first_name}</b>! 👋",
    "start_menu": "menu",  # command yang ditampilin setelah /start ("" = nonaktif)
    "commands": {"menu": {"text": "Menu", "per_row": 3, "buttons": []}},
    "posts": {},  # pesan yang sudah diposting: {command: {chat: message_id}}
}

_cache = {"mtime": 0.0, "data": None}


def _migrate(data: dict) -> bool:
    """Config lama: command 'list' diganti jadi 'menu' (beserta catatan post-nya)."""
    cmds = data.get("commands", {})
    if "list" in cmds and "menu" not in cmds:
        cmds["menu"] = cmds.pop("list")
        posts = data.get("posts", {})
        if "list" in posts:
            posts["menu"] = posts.pop("list")
        return True
    return False


# ---------------------------------------------------------------- config ----
def load_config() -> dict:
    """Baca config.json; reload otomatis kalau file berubah (mis. lewat manage.py)."""
    try:
        mtime = CONFIG_PATH.stat().st_mtime
    except FileNotFoundError:
        cfg = copy.deepcopy(DEFAULT)
        save_config(cfg)
        return cfg
    if _cache["data"] is None or mtime != _cache["mtime"]:
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            if _cache["data"] is None:
                raise SystemExit(f"config.json rusak (JSON nggak valid): {e}")
            print(f"config.json rusak, pakai versi terakhir: {e}")
            return _cache["data"]
        for k, v in DEFAULT.items():
            data.setdefault(k, copy.deepcopy(v))
        if _migrate(data):
            save_config(data)
            return data
        _cache["data"], _cache["mtime"] = data, mtime
    return _cache["data"]


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(CONFIG_PATH)  # atomic, bot nggak pernah baca file setengah jadi
    _cache["data"], _cache["mtime"] = cfg, CONFIG_PATH.stat().st_mtime


def get_token() -> str:
    """Token dari env TOKEN, kalau nggak ada dari config.json."""
    token = (os.environ.get("TOKEN") or load_config().get("token", "")).strip()
    if not token or token == TOKEN_PLACEHOLDER:
        raise SystemExit("Token kosong. Jalanin: python Src/manage.py token <TOKEN>")
    return token


def get_admin_ids() -> set:
    """ID admin dari env ADMINS (pisah koma), kalau nggak ada dari config.json."""
    raw = os.environ.get("ADMINS")
    ids = raw.split(",") if raw else load_config().get("admin_ids", [])
    out = set()
    for x in ids:
        try:
            out.add(int(str(x).strip()))
        except ValueError:
            pass
    return out


# --------------------------------------------------------------- helpers ----
class _Safe(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def fmt_text(text, first_name="", user_id="") -> str:
    try:
        return str(text).format_map(_Safe(first_name=first_name, user_id=user_id))
    except Exception:
        return str(text)


def valid_link(link: str) -> bool:
    return link.startswith(("http://", "https://", "tg://")) and " " not in link


def chunk(items, n):
    n = max(1, n)
    return [items[i:i + n] for i in range(0, len(items), n)]


def flat_buttons(entry: dict) -> list:
    return [b for row in entry.get("buttons", []) for b in row]


def btn_count(entry: dict) -> int:
    return sum(len(r) for r in entry.get("buttons", []))


def relayout(entry: dict, n=None) -> None:
    """Susun ulang semua tombol jadi grid n tombol per baris."""
    rows = entry.get("buttons", [])
    n = n or entry.get("per_row") or max((len(r) for r in rows), default=1)
    entry["buttons"] = chunk(flat_buttons(entry), n)


def add_buttons(entry: dict, pairs) -> None:
    """Tambah tombol (teks, url): isi baris terakhir dulu sampai per_row, lalu baris baru."""
    n = entry.get("per_row") or 1
    rows = entry.setdefault("buttons", [])
    for text, url in pairs:
        b = {"text": text, "url": url}
        if rows and len(rows[-1]) < n:
            rows[-1].append(b)
        else:
            rows.append([b])


def remove_buttons(entry: dict, numbers) -> None:
    """Hapus tombol berdasarkan nomor urut (mulai 1). Susunan baris dipertahankan."""
    nums, i, rows = set(numbers), 0, []
    for row in entry.get("buttons", []):
        kept = []
        for b in row:
            i += 1
            if i not in nums:
                kept.append(b)
        if kept:
            rows.append(kept)
    entry["buttons"] = rows


# ------------------------------------------- posting via HTTP (tanpa PTB) ----
def _api(token, method, payload):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        return json.load(e)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "description": f"koneksi gagal: {e}"}


def publish_http(name: str, target=None, force_new=False) -> str:
    """Kirim command ke channel/grup. Kalau sudah pernah diposting, pesan lama di-edit.
    Return pesan status, raise RuntimeError kalau gagal."""
    cfg = load_config()
    entry = cfg["commands"].get(name)
    if not entry:
        raise RuntimeError(f"Command /{name} nggak ada.")
    target = target or cfg.get("chat_id")
    if not target:
        raise RuntimeError("Target kosong. Isi chat_id (menu 4) atau tulis @channel.")
    token = get_token()

    chat = int(target) if str(target).lstrip("-").isdigit() else target
    rows = [[{"text": b["text"], "url": b["url"]} for b in row] for row in entry.get("buttons", [])]
    payload = {"chat_id": chat, "text": fmt_text(entry["text"]), "parse_mode": "HTML"}
    if rows:
        payload["reply_markup"] = {"inline_keyboard": rows}

    posts = cfg.setdefault("posts", {}).setdefault(name, {})
    key = str(target).lower()
    mid = posts.get(key)
    if mid and not force_new:
        r = _api(token, "editMessageText",
                 {**payload, "message_id": mid, "reply_markup": {"inline_keyboard": rows}})
        desc = r.get("description", "").lower()
        if r.get("ok") or "not modified" in desc:
            return "Pesan lama di-update."
        if "koneksi gagal" in desc:
            raise RuntimeError(r["description"])
    r = _api(token, "sendMessage", payload)
    if not r.get("ok"):
        raise RuntimeError(f"Gagal: {r.get('description')}")
    posts[key] = r["result"]["message_id"]
    save_config(cfg)
    return "Terkirim. Pin pesannya biar selalu di atas."
