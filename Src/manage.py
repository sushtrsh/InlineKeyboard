"""
manage.py - Setup & kelola bot dari terminal (Termux). Semua disimpan ke Config/config.json.
Bikin command/tombol juga bisa langsung di Telegram: /admin

Menu:     python Src/manage.py
Langsung: python Src/manage.py token <TOKEN> | add-admin <ID> | del-admin <ID> | chat <@channel|ID>
          python Src/manage.py list | run | import <bots.json> | post <command> [@channel] [--new]
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import common
from common import load_config as load, save_config as save

BOT_PATH = common.ROOT / "Src" / "bot.py"
NAME_OK = re.compile(r"[a-z0-9_]{1,32}")


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        raise SystemExit


# ------------------------------------------------------------------ setup ---
def set_token(token: str):
    if ":" not in token:
        print("❌ Format token nggak valid (123456:ABC...).")
        return
    cfg = load()
    cfg["token"] = token.strip()
    save(cfg)
    print("✅ Token disimpan.")


def add_admin(uid: str):
    if not uid.lstrip("-").isdigit():
        print("❌ ID harus angka (cek lewat /id di bot).")
        return
    cfg = load()
    if int(uid) in cfg["admin_ids"]:
        print("ℹ️  Udah jadi admin.")
        return
    cfg["admin_ids"].append(int(uid))
    save(cfg)
    print(f"✅ Admin {uid} ditambahkan.")


def del_admin(uid: str):
    cfg = load()
    try:
        cfg["admin_ids"].remove(int(uid))
    except ValueError:
        print("❌ ID nggak ada di daftar admin.")
        return
    save(cfg)
    print(f"✅ Admin {uid} dihapus.")


def set_chat(chat: str):
    if not (chat.startswith("@") or chat.lstrip("-").isdigit()):
        print("❌ Isi @username channel/grup atau ID angka (-100...).")
        return
    cfg = load()
    cfg["chat_id"] = chat
    save(cfg)
    print("✅ chat_id disimpan.")


def show():
    cfg = load()
    t = cfg["token"]
    print(f"\nToken  : {t[:6] + '...' + t[-4:] if t else '(kosong)'}")
    print(f"Admin  : {cfg['admin_ids'] or '(belum ada)'}")
    print(f"Chat ID: {cfg.get('chat_id') or '(belum diisi)'}")
    cmds = cfg["commands"]
    print("Command: " + (", ".join(f"/{c} ({common.btn_count(e)})" for c, e in cmds.items()) or "(belum ada)"))
    print()


def run_bot():
    subprocess.run([sys.executable, str(BOT_PATH)])


# ------------------------------------------------- command & tombol (menu) ---
def show_command(name: str, entry: dict):
    print(f"\n/{name} | per baris: {entry.get('per_row') or '-'}")
    print("Teks:", entry["text"].replace("\n", " / ")[:100])
    n = 0
    for r, row in enumerate(entry.get("buttons", []), 1):
        for b in row:
            n += 1
            print(f"{n:>2}. [baris {r}] {b['text']} -> {b['url']}")
    if not n:
        print("(belum ada tombol)")


def pick_command():
    cfg = load()
    names = list(cfg["commands"])
    print("\nCommand:")
    for i, n in enumerate(names, 1):
        print(f"{i}. /{n} ({common.btn_count(cfg['commands'][n])} tombol)")
    raw = ask("Nomor atau nama command (kosong = batal): ").lstrip("/").lower()
    if not raw:
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(names):
        return names[int(raw) - 1]
    if raw in cfg["commands"]:
        return raw
    if not NAME_OK.fullmatch(raw) or raw in common.RESERVED:
        print("❌ Nama nggak valid / dipakai command bawaan (huruf kecil, angka, _).")
        return None
    if ask(f"/{raw} belum ada. Bikin? (y/n): ").lower() == "y":
        cfg["commands"][raw] = {"text": f"Teks untuk /{raw}", "per_row": 3, "buttons": []}
        save(cfg)
        return raw
    return None


def add_flow(cfg, entry) -> bool:
    changed = False
    while True:
        text = ask("Nama tombol (kosong = selesai): ")
        if not text:
            return changed
        url = ask("Link: ")
        if not common.valid_link(url):
            print("❌ Link harus diawali http:// atau https://")
            continue
        common.add_buttons(entry, [(text, url)])
        save(cfg)
        changed = True
        print(f"+ {text} ditambah")


def delete_flow(cfg, entry) -> bool:
    raw = ask("Nomor tombol yang dihapus (pisah koma, misal 2,4): ")
    try:
        nums = {int(x) for x in raw.split(",")}
        total = common.btn_count(entry)
        if any(n < 1 or n > total for n in nums):
            raise ValueError
    except ValueError:
        print("❌ Input nggak valid, batal.")
        return False
    common.remove_buttons(entry, nums)
    save(cfg)
    print(f"- {len(nums)} tombol dihapus")
    return True


def edit_flow(cfg, entry) -> bool:
    try:
        i = int(ask("Nomor tombol yang diedit: "))
        flat = common.flat_buttons(entry)
        b = flat[i - 1] if i >= 1 else None
        if b is None:
            raise IndexError
    except (ValueError, IndexError):
        print("❌ Nomor nggak valid.")
        return False
    b["text"] = ask(f"Nama baru [{b['text']}]: ") or b["text"]
    url = ask(f"Link baru [{b['url']}]: ")
    if url:
        if common.valid_link(url):
            b["url"] = url
        else:
            print("❌ Link nggak valid, link lama dipertahankan.")
    save(cfg)
    return True


def move_flow(cfg, entry) -> bool:
    try:
        a = int(ask("Pindah nomor: ")) - 1
        b = int(ask("Ke posisi: ")) - 1
        flat = common.flat_buttons(entry)
        if not (0 <= a < len(flat) and 0 <= b < len(flat)):
            raise IndexError
    except (ValueError, IndexError):
        print("❌ Input nggak valid.")
        return False
    flat.insert(b, flat.pop(a))
    entry["buttons"] = [[x] for x in flat]
    common.relayout(entry)
    save(cfg)
    return True


def text_flow(cfg, entry) -> bool:
    t = ask("Teks pesan baru (HTML boleh, kosong = batal): ")
    if not t:
        return False
    entry["text"] = t.replace("\\n", "\n")
    save(cfg)
    return True


def per_row_flow(cfg, entry) -> bool:
    p = ask(f"Tombol per baris 1-8 [{entry.get('per_row') or '-'}]: ")
    if not (p.isdigit() and 1 <= int(p) <= 8):
        return False
    entry["per_row"] = int(p)
    common.relayout(entry, int(p))
    save(cfg)
    return True


def sync_channel(name: str):
    """Update pesan yang sudah diposting ke channel (kalau ada)."""
    for target in list(load().get("posts", {}).get(name, {})):
        try:
            print(f"{target}: {common.publish_http(name, target)}")
        except RuntimeError as e:
            print(f"{target}: {e}")


def buttons_menu(name: str):
    dirty = False
    flows = {"1": add_flow, "2": delete_flow, "3": edit_flow, "4": move_flow,
             "5": text_flow, "6": per_row_flow}
    while True:
        cfg = load()
        entry = cfg["commands"].get(name)
        if entry is None:
            return
        show_command(name, entry)
        print("\n1. Tambah  2. Hapus  3. Edit  4. Pindah  5. Teks pesan  6. Tombol per baris  0. Kembali")
        c = ask("Pilih: ")
        if c == "0":
            break
        if c in flows:
            dirty |= bool(flows[c](cfg, entry))
    if dirty and load().get("posts", {}).get(name):
        if ask("Update pesan di channel sekarang? (y/n): ").lower() == "y":
            sync_channel(name)


def commands_menu():
    name = pick_command()
    if name:
        buttons_menu(name)


# ------------------------------------------------------------------- post ---
def post(name: str, target: str = None, force_new=False):
    try:
        print("✅", common.publish_http(name, target, force_new))
    except (RuntimeError, SystemExit) as e:
        print("❌", e)


def post_menu():
    name = pick_command()
    if not name:
        return
    default = load().get("chat_id") or ""
    target = ask(f"Target @channel/ID [{default or 'belum ada'}]: ") or default
    force = ask("Kirim pesan BARU (bukan update)? (y/n): ").lower() == "y"
    post(name, target, force)


# ----------------------------------------------------------------- import ---
def import_old(path: str):
    """Impor daftar lama (bots.json: title, per_row, items) jadi command /menu."""
    p = Path(path)
    if not p.exists():
        print(f"❌ File {path} nggak ada.")
        return
    try:
        old = json.loads(p.read_text(encoding="utf-8"))
        items = [{"text": i["name"], "url": i["link"]} for i in old.get("items", [])]
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
        print(f"❌ Format bots.json nggak dikenali: {e}")
        return
    n = old.get("per_row") or 3
    cfg = load()
    cfg["commands"]["menu"] = {"text": old.get("title", "List Bot"), "per_row": n,
                               "buttons": common.chunk(items, n)}
    save(cfg)
    print(f"✅ {len(items)} tombol diimpor ke /menu.")


# ------------------------------------------------------------------- menu ---
def menu():
    acts = {
        "1": ("Set token", lambda: set_token(ask("Token: "))),
        "2": ("Tambah admin", lambda: add_admin(ask("User ID: "))),
        "3": ("Hapus admin", lambda: del_admin(ask("User ID: "))),
        "4": ("Set chat_id (tujuan post)", lambda: set_chat(ask("@channel atau ID: "))),
        "5": ("Kelola command & tombol", commands_menu),
        "6": ("Kirim / update ke channel", post_menu),
        "7": ("Lihat config", show),
        "8": ("Impor daftar lama (bots.json)", lambda: import_old(ask("Path bots.json: "))),
        "9": ("Jalanin bot", run_bot),
    }
    while True:
        print("\n=== Manage Bot ===")
        for k, (label, _) in acts.items():
            print(f" {k}. {label}")
        print(" 0. Keluar")
        c = ask("> ")
        if c == "0":
            break
        acts.get(c, ("", lambda: print("Pilihan nggak valid.")))[1]()


if __name__ == "__main__":
    load()
    a = sys.argv[1:]
    cli = {"token": set_token, "add-admin": add_admin, "del-admin": del_admin,
           "chat": set_chat, "import": import_old}
    if not a:
        menu()
    elif a[0] in cli and len(a) > 1:
        cli[a[0]](a[1])
    elif a[0] == "list":
        show()
    elif a[0] == "run":
        run_bot()
    elif a[0] == "post" and len(a) > 1:
        rest = [x for x in a[2:] if x != "--new"]
        post(a[1].lstrip("/").lower(), rest[0] if rest else None, "--new" in a)
    else:
        print(__doc__)
