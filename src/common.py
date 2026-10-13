"""Helper bersama untuk bot.py, manager.py, dan post.py."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"  # file lokal (config, daftar, state), nggak ikut git
BOTS_FILE = DATA_DIR / "bots.json"
CONFIG_FILE = DATA_DIR / "config.json"
STATE_FILE = DATA_DIR / "state.json"

TOKEN_PLACEHOLDER = "ISI_TOKEN_DARI_BOTFATHER"


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path.name} rusak (JSON nggak valid): {e}")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load_bots():
    d = read_json(BOTS_FILE, {})
    d.setdefault("title", "List Bot")
    d.setdefault("per_row", 3)
    d.setdefault("items", [])
    return d


def save_bots(d):
    write_json(BOTS_FILE, d)


def load_config():
    return read_json(CONFIG_FILE, {})


def save_config(cfg):
    write_json(CONFIG_FILE, cfg)


def get_token():
    """Token dari env TOKEN, kalau nggak ada dari config.json."""
    token = (os.environ.get("TOKEN") or load_config().get("token", "")).strip()
    if not token or token == TOKEN_PLACEHOLDER:
        raise SystemExit(
            "Token belum diisi. Isi di data/config.json (lihat examples/config.example.json) "
            "atau set env TOKEN."
        )
    return token


def get_admins():
    """ID admin dari env ADMINS (pisah koma), kalau nggak ada dari config.json."""
    raw = os.environ.get("ADMINS")
    ids = raw.split(",") if raw else load_config().get("admins", [])
    return {int(x) for x in ids if str(x).strip()}


def valid_link(link):
    """Link apa aja boleh, asal diawali http://, https://, atau tg://."""
    return link.startswith(("http://", "https://", "tg://")) and " " not in link


def chunk(items, n):
    return [items[i:i + n] for i in range(0, len(items), n)]
