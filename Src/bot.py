"""
bot.py - Bot Telegram simpel. Admin ngatur bot LANGSUNG dari Telegram,
semuanya disimpan ke Config/config.json.

Command ADMIN (hanya admin_ids, hanya di chat pribadi):
  /admin            bantuan
  /inlinekeyboard   bikin command + tombol link (atau buka editornya)
  /edit             editor: ganti teks, tambah/hapus tombol, susunan, hapus command
  /addcmd           bikin command teks biasa
  /delcmd           hapus command
  /post             kirim command ke channel/grup (kirim kedua kalinya = update pesan lama)
  /batal            batalin input yang lagi ditunggu

Command USER (semua orang): /start (sapaan + menu) /help /id + command buatan admin (mis. /menu).

Butuh: pip install "python-telegram-bot>=21"
"""
import copy
import logging
import os
import re
import traceback

import httpx
from telegram import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

import common
from common import btn_count, load_config, save_config

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger("bot")


def is_admin(uid: int) -> bool:
    return uid in common.get_admin_ids()


# ---------------------------------------------------------------- helpers ---
def fmt(text: str, user) -> str:
    return common.fmt_text(
        text, user.first_name if user else "", user.id if user else "")


def user_markup(entry: dict, name: str = None, admin: bool = False):
    """Tombol link buat user. Admin (di chat pribadi) dapat tambahan tombol ⚙️ Edit."""
    rows = [[InlineKeyboardButton(b["text"], url=b["url"]) for b in row]
            for row in entry.get("buttons", [])]
    if admin and name:
        rows.append([InlineKeyboardButton("⚙️ Edit", callback_data=f"e:open:{name}")])
    return InlineKeyboardMarkup(rows) if rows else None


async def send_custom(bot, chat_id, entry: dict, user=None, name=None, admin=False):
    """Kirim satu command buatan: teks (HTML) + tombol link (opsional)."""
    await bot.send_message(
        chat_id, fmt(entry.get("text", ""), user), parse_mode="HTML",
        reply_markup=user_markup(entry, name, admin),
    )


def desc_of(entry: dict) -> str:
    first = re.sub(r"<[^>]+>", "", entry.get("text", "")).strip().split("\n")[0]
    return (first or "Command")[:60]


LINK_ROW = re.compile(r"=\s*(https?|tg)://")
NAME_OK = re.compile(r"[a-z0-9_]{1,32}")


def split_lines(lines: list[str]):
    """Pisahin baris teks vs baris tombol (baris yang berisi Teks=https://link)."""
    text_lines, rows = [], []
    for line in lines:
        if LINK_ROW.search(line):
            row = []
            for item in line.split(";"):
                if "=" in item:
                    t, u = item.split("=", 1)
                    if t.strip() and u.strip():
                        row.append({"text": t.strip(), "url": u.strip()})
            if row:
                rows.append(row)
        else:
            text_lines.append(line)
    return text_lines, rows


def parse_quick(text: str):
    """Baris 'Nama | link' -> (pasangan valid, baris yang dilewati)."""
    pairs, bad = [], []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            t, u = [x.strip() for x in line.split("|", 1)]
            if t and common.valid_link(u):
                pairs.append((t, u))
                continue
        bad.append(line)
    return pairs, bad


def valid_name(name: str):
    """Return pesan error, atau None kalau nama valid."""
    if not NAME_OK.fullmatch(name):
        return "❌ Nama: huruf kecil, angka, underscore (maks 32)."
    if name in common.RESERVED:
        return f"❌ /{name} dipakai command bawaan, pilih nama lain."
    return None


# ----------------------------------------------------------------- jaringan -
def make_request(read_timeout):
    kw = {}
    if os.environ.get("NET_TWEAKS") == "1":
        # Opsional: paksa IPv4 dan matiin keep-alive (kalau jaringan sering putus)
        kw["httpx_kwargs"] = {"transport": httpx.AsyncHTTPTransport(
            local_address="0.0.0.0", retries=2,
            limits=httpx.Limits(max_keepalive_connections=0))}
    return HTTPXRequest(connect_timeout=20, read_timeout=read_timeout,
                        write_timeout=30, pool_timeout=30, **kw)


async def on_error(update, ctx: ContextTypes.DEFAULT_TYPE):
    err = ctx.error
    if isinstance(err, (NetworkError, TimedOut)):
        # Putus koneksi sesaat, PTB otomatis nyoba lagi. Cukup satu baris.
        log.warning("Jaringan putus sesaat (%s), nyoba lagi...", type(err).__name__)
        return
    log.error("Error: %r", err)
    traceback.print_exception(err)


# -------------------------------------------------------------- menu "/" ----
async def sync_commands(bot):
    """User lihat command user, admin lihat semuanya."""
    cfg = load_config()
    user_cmds = [
        BotCommand("start", "Mulai bot"),
        BotCommand("help", "Daftar command"),
        BotCommand("id", "Lihat ID kamu"),
    ] + [BotCommand(n, desc_of(e)) for n, e in cfg.get("commands", {}).items()]
    admin_cmds = user_cmds + [
        BotCommand("admin", "Panel admin"),
        BotCommand("inlinekeyboard", "Bikin command + tombol"),
        BotCommand("edit", "Edit command langsung"),
        BotCommand("addcmd", "Bikin command teks"),
        BotCommand("delcmd", "Hapus command"),
        BotCommand("post", "Kirim / update di channel"),
        BotCommand("batal", "Batalin input"),
    ]
    await bot.set_my_commands(user_cmds[:100], scope=BotCommandScopeDefault())
    for aid in common.get_admin_ids():
        try:
            await bot.set_my_commands(admin_cmds[:100], scope=BotCommandScopeChat(aid))
        except Exception as e:  # admin belum pernah /start bot
            log.warning("Menu admin %s dilewati: %s", aid, e)


async def resync(bot):
    try:
        await sync_commands(bot)
    except Exception as e:
        log.error("Sync menu gagal: %s", e)


# ------------------------------------------------------- posting ke channel -
def _chat(target):
    t = str(target)
    return int(t) if t.lstrip("-").isdigit() else t


async def _edit_post(bot, chat, mid, entry):
    await bot.edit_message_text(
        fmt(entry["text"], None), chat_id=_chat(chat), message_id=mid, parse_mode="HTML",
        reply_markup=user_markup(entry) or InlineKeyboardMarkup([]),
    )


async def publish(bot, name: str, target, force_new=False) -> str:
    """Kirim command ke channel. Kalau sudah pernah, pesan lama di-edit (bukan kirim baru)."""
    cfg = load_config()
    entry = cfg["commands"][name]
    key = str(target).lower()
    posts = cfg.setdefault("posts", {}).setdefault(name, {})
    mid = posts.get(key)
    if mid and not force_new:
        try:
            await _edit_post(bot, key, mid, entry)
            return "Pesan lama di-update."
        except BadRequest as e:
            if "not modified" in str(e).lower():
                return "Pesan lama di-update."
            log.warning("Edit gagal (%s), kirim pesan baru.", e)
    m = await bot.send_message(
        _chat(target), fmt(entry["text"], None), parse_mode="HTML",
        reply_markup=user_markup(entry))
    posts[key] = m.message_id
    save_config(cfg)
    return f"Terkirim ke {target}. Pin pesannya biar selalu di atas."


async def refresh_posts(bot, name: str):
    """Setelah command diedit, update semua pesan yang pernah diposting ke channel."""
    cfg = load_config()
    entry = cfg.get("commands", {}).get(name)
    posts = cfg.get("posts", {}).get(name, {})
    if not entry or not posts:
        return
    changed = False
    for key, mid in list(posts.items()):
        try:
            await _edit_post(bot, key, mid, entry)
        except BadRequest as e:
            msg = str(e).lower()
            if "not modified" in msg:
                continue
            log.warning("Update post %s gagal: %s", key, e)
            if "not found" in msg or "can't be edited" in msg:
                del posts[key]  # pesan sudah dihapus, lupain
                changed = True
        except Exception as e:
            log.warning("Update post %s gagal: %s", key, e)
    if changed:
        save_config(cfg)


# ------------------------------------------------------------ USER commands -
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Sapaan, lalu tampilin menu (command yang namanya di config 'start_menu')."""
    cfg, msg, user = load_config(), update.effective_message, update.effective_user
    await msg.reply_text(fmt(cfg.get("start_text", "Halo!"), user), parse_mode="HTML")
    name = cfg.get("start_menu", "menu")
    entry = cfg.get("commands", {}).get(name) if name else None
    if entry and entry.get("buttons"):  # menu kosong nggak usah ditampilin
        admin = msg.chat.type == "private" and is_admin(user.id)
        await send_custom(ctx.bot, msg.chat_id, entry, user, name, admin)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = ["/start - Mulai bot", "/help - Daftar command", "/id - Lihat ID kamu"]
    for n, e in load_config().get("commands", {}).items():
        lines.append(f"/{n} - {desc_of(e)}")
    if is_admin(update.effective_user.id):
        lines.append("\n🛠️ Kamu admin, ketik /admin")
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # <code> bikin angkanya bisa disalin dengan sekali tap
    u, c = update.effective_user, update.effective_chat
    await update.effective_message.reply_text(
        f"User ID: <code>{u.id}</code>\nChat ID: <code>{c.id}</code>", parse_mode="HTML"
    )


USER_CMDS = {"start": cmd_start, "help": cmd_help, "id": cmd_id}

# ------------------------------------------------------------------ EDITOR --
def editor_markup(name: str, entry: dict, mode: str = "edit"):
    """Keyboard editor: tombol asli + baris kontrol. mode: edit | del | kill | done."""
    if mode == "done":
        return user_markup(entry)
    rows = []
    for r, row in enumerate(entry.get("buttons", [])):
        if mode == "del":
            rows.append([
                InlineKeyboardButton("🗑 " + b["text"], callback_data=f"e:rm:{name}:{r}:{c}")
                for c, b in enumerate(row)
            ])
        elif mode == "edit":
            rows.append([InlineKeyboardButton(b["text"], url=b["url"]) for b in row])

    def B(label, action):
        return InlineKeyboardButton(label, callback_data=f"e:{action}:{name}")

    if mode == "edit":
        second = [B("➕ Tombol", "add")]
        if entry.get("buttons"):
            second.append(B("🗑 Tombol", "del"))
        rows += [
            [B("✏️ Teks", "txt"), B("⚡ Cepat", "quick"), B(f"🔢 {entry.get('per_row') or '-'}/baris", "pr")],
            second,
            [B("✅ Selesai", "done"), B("❌ Hapus cmd", "kill")],
        ]
    elif mode == "del":
        rows.append([B("⬅️ Batal", "back")])
    elif mode == "kill":
        rows.append([B(f"⚠️ Ya, hapus /{name}", "killy"), B("⬅️ Batal", "back")])
    return InlineKeyboardMarkup(rows)


async def open_editor(bot, chat_id, name: str, user):
    entry = load_config()["commands"][name]
    await bot.send_message(
        chat_id, fmt(entry["text"], user), parse_mode="HTML",
        reply_markup=editor_markup(name, entry, "edit"),
    )


async def render(bot, chat_id, message_id, name: str, entry: dict, mode: str, user):
    """Edit pesan editor di tempat. 'message is not modified' diabaikan."""
    try:
        await bot.edit_message_text(
            fmt(entry["text"], user), chat_id=chat_id, message_id=message_id,
            parse_mode="HTML", reply_markup=editor_markup(name, entry, mode),
        )
    except Exception as e:
        if "not modified" not in str(e).lower():
            raise


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    parts = (q.data or "").split(":")
    if parts[0] != "e" or len(parts) < 3:
        await q.answer()
        return
    if not is_admin(q.from_user.id):  # tombol bisa kebawa lewat forward
        await q.answer("⛔ Khusus admin.", show_alert=True)
        return

    act, name, rest = parts[1], parts[2], parts[3:]
    cfg = load_config()
    entry = cfg.get("commands", {}).get(name)
    if not entry:
        await q.answer("Command nggak ketemu.", show_alert=True)
        return

    bot, chat_id, mid, user = ctx.bot, q.message.chat_id, q.message.message_id, q.from_user
    await q.answer()

    if act in ("open", "back"):
        await render(bot, chat_id, mid, name, entry, "edit", user)
    elif act in ("del", "kill", "done"):
        await render(bot, chat_id, mid, name, entry, act, user)
    elif act == "rm":
        try:
            r, c = int(rest[0]), int(rest[1])
            del entry["buttons"][r][c]
            if not entry["buttons"][r]:
                del entry["buttons"][r]
        except (IndexError, ValueError):
            pass
        save_config(cfg)
        await render(bot, chat_id, mid, name, entry, "del" if btn_count(entry) else "edit", user)
        await refresh_posts(bot, name)
    elif act == "pr":  # ganti jumlah tombol per baris: 1 -> 2 -> 3 -> 4 -> 1
        n = (entry.get("per_row") or 0) % 4 + 1
        entry["per_row"] = n
        common.relayout(entry, n)
        save_config(cfg)
        await render(bot, chat_id, mid, name, entry, "edit", user)
        await refresh_posts(bot, name)
    elif act == "killy":
        cfg["commands"].pop(name, None)
        cfg.get("posts", {}).pop(name, None)
        save_config(cfg)
        await resync(bot)
        await bot.edit_message_text(f"🗑 /{name} dihapus.", chat_id=chat_id, message_id=mid)
    elif act == "txt":
        ctx.user_data["await"] = {"mode": "text", "name": name, "chat": chat_id, "mid": mid}
        await bot.send_message(chat_id, "✏️ Kirim teks baru (boleh HTML & banyak baris).\n/batal buat batal.")
    elif act == "add":
        ctx.user_data["await"] = {"mode": "row", "name": name, "chat": chat_id, "mid": mid}
        await bot.send_message(
            chat_id,
            "➕ Kirim baris tombol baru:\n\nTombol1=https://link1 ; Tombol2=https://link2\n"
            "Tombol3=https://link3\n\nSatu baris = satu baris tombol. /batal buat batal.",
        )
    elif act == "quick":
        ctx.user_data["await"] = {"mode": "quick", "name": name, "chat": chat_id, "mid": mid}
        await bot.send_message(
            chat_id,
            "⚡ Kirim satu atau banyak tombol, satu per baris:\n\nNama | https://link\n"
            "Nama2 | https://link2\n\nOtomatis disusun sesuai tombol per baris (🔢). /batal buat batal.",
        )


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Nangkep jawaban admin setelah tekan ✏️ Teks / ➕ Tombol / ⚡ Cepat."""
    msg, st = update.effective_message, ctx.user_data.get("await")
    if not st or not is_admin(update.effective_user.id):
        return
    cfg = load_config()
    entry = cfg.get("commands", {}).get(st["name"])
    if not entry:
        ctx.user_data.pop("await", None)
        return

    old_text, old_buttons = entry["text"], copy.deepcopy(entry.get("buttons", []))
    skipped = 0
    if st["mode"] == "text":
        entry["text"] = msg.text.strip()
    elif st["mode"] == "quick":
        pairs, bad = parse_quick(msg.text)
        if not pairs:
            await msg.reply_text("❌ Nggak ada baris valid. Format per baris: Nama | https://link")
            return
        common.add_buttons(entry, pairs)
        skipped = len(bad)
    else:
        _, rows = split_lines(msg.text.split("\n"))
        if not rows:
            await msg.reply_text("❌ Nggak ada tombol valid. Format: Teks=https://link ; Teks2=https://link2")
            return
        entry["buttons"] = old_buttons + rows

    try:
        await render(ctx.bot, st["chat"], st["mid"], st["name"], entry, "edit", update.effective_user)
    except Exception as e:  # HTML / link salah -> balikin
        entry["text"], entry["buttons"] = old_text, old_buttons
        await msg.reply_text(f"❌ Gagal: {e}\nCoba kirim lagi, atau /batal.")
        return

    save_config(cfg)
    ctx.user_data.pop("await", None)
    await resync(ctx.bot)
    await refresh_posts(ctx.bot, st["name"])
    try:
        await msg.delete()
    except Exception:
        pass
    if skipped:
        await ctx.bot.send_message(st["chat"], f"⚠️ {skipped} baris dilewati (format harus Nama | https://link).")


# ----------------------------------------------------------- ADMIN commands -
ADMIN_HELP = (
    "<b>Command admin</b>\n"
    "/inlinekeyboard <i>nama</i> - bikin command + tombol (langsung kebuka editornya)\n"
    "/edit <i>[nama]</i> - editor: teks, tombol, susunan per baris\n"
    "/addcmd <i>nama teks</i> - bikin command teks biasa\n"
    "/delcmd <i>nama</i> - hapus command\n"
    "/post <i>nama [@channel] [baru]</i> - kirim ke channel; kedua kalinya update pesan lama\n"
    "/batal - batalin input yang lagi ditunggu\n\n"
    "Admin yang jalanin command buatan (mis. /menu) di chat pribadi dapat tombol ⚙️ Edit."
)

KEYBOARD_USAGE = (
    "Cara cepat: /inlinekeyboard nama  → langsung kebuka editor, tinggal ketuk-ketuk.\n\n"
    "Atau bikin sekaligus (kirim dalam SATU pesan):\n\n"
    "/inlinekeyboard nama\n"
    "Teks pesan (boleh HTML & banyak baris)\n"
    "Tombol1=https://link1 ; Tombol2=https://link2\n"
    "Tombol3=https://link3\n\n"
    "• Baris yang berisi link = satu baris tombol (pisah tombol pakai  ;)\n"
    "• Baris tanpa link = teks pesan"
)


async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(ADMIN_HELP, parse_mode="HTML")


async def cmd_batal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("👌 Dibatalin.")  # state udah direset di on_command


async def cmd_inlinekeyboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg, user = update.effective_message, update.effective_user
    lines = msg.text.split("\n")
    head = lines[0].split()
    if len(head) < 2:
        await msg.reply_text(KEYBOARD_USAGE)
        return
    name = head[1].lstrip("/").lower()
    cfg = load_config()
    old = cfg.get("commands", {}).get(name)
    if old is None and (err := valid_name(name)):
        await msg.reply_text(err)
        return

    text_lines, rows = split_lines(lines[1:])
    text = "\n".join(text_lines).strip()

    if not text and not rows:  # cuma nama -> buka editor (bikin dulu kalau belum ada)
        if old is None:
            cfg.setdefault("commands", {})[name] = {
                "text": f"Teks untuk /{name} — ketuk ✏️ Teks buat ganti.", "per_row": 3, "buttons": []}
            save_config(cfg)
            await resync(ctx.bot)
        await open_editor(ctx.bot, msg.chat_id, name, user)
        return

    old = old or {}
    entry = {**old, "text": text or old.get("text") or f"Teks untuk /{name}",
             "buttons": rows or old.get("buttons", [])}
    try:  # kirim editor sekaligus validasi (HTML/link salah ketahuan di sini)
        await ctx.bot.send_message(
            msg.chat_id, fmt(entry["text"], user), parse_mode="HTML",
            reply_markup=editor_markup(name, entry, "edit"),
        )
    except Exception as e:
        await msg.reply_text(f"❌ Gagal: {e}\nNggak disimpan.")
        return
    cfg.setdefault("commands", {})[name] = entry
    save_config(cfg)
    await resync(ctx.bot)
    await refresh_posts(ctx.bot, name)


async def cmd_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg, parts = update.effective_message, update.effective_message.text.split()
    cmds = load_config().get("commands", {})
    if len(parts) >= 2:
        name = parts[1].lstrip("/").lower()
        if name not in cmds:
            await msg.reply_text("❌ Command nggak ketemu. Ketik /edit buat lihat daftar.")
            return
        await open_editor(ctx.bot, msg.chat_id, name, update.effective_user)
        return
    if not cmds:
        await msg.reply_text("Belum ada command buatan. Bikin: /inlinekeyboard nama")
        return
    names = list(cmds)
    rows = [
        [InlineKeyboardButton(f"/{n} {'🔘' + str(btn_count(cmds[n])) if cmds[n].get('buttons') else '📝'}",
                              callback_data=f"e:open:{n}") for n in names[i:i + 2]]
        for i in range(0, len(names), 2)
    ]
    await msg.reply_text("Pilih command yang mau diedit:", reply_markup=InlineKeyboardMarkup(rows))


async def cmd_addcmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    parts = msg.text.split(None, 2)
    if len(parts) < 3:
        await msg.reply_text("Format: /addcmd nama teks pesan")
        return
    name = parts[1].lstrip("/").lower()
    if err := valid_name(name):
        await msg.reply_text(err)
        return
    cfg = load_config()
    old = cfg.get("commands", {}).get(name, {})
    entry = {**old, "text": parts[2].strip(), "buttons": old.get("buttons", [])}
    try:
        await ctx.bot.send_message(msg.chat_id, fmt(entry["text"], update.effective_user), parse_mode="HTML")
    except Exception as e:
        await msg.reply_text(f"❌ Gagal: {e}\nNggak disimpan.")
        return
    cfg.setdefault("commands", {})[name] = entry
    save_config(cfg)
    await resync(ctx.bot)
    await refresh_posts(ctx.bot, name)
    await msg.reply_text(f"✅ /{name} disimpan. Mau nambah tombol? /edit {name}")


async def cmd_delcmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if len(msg.text.split()) < 2:
        await msg.reply_text("Format: /delcmd nama")
        return
    name = msg.text.split()[1].lstrip("/").lower()
    cfg = load_config()
    if cfg.get("commands", {}).pop(name, None) is None:
        await msg.reply_text("❌ Command nggak ketemu.")
        return
    cfg.get("posts", {}).pop(name, None)
    save_config(cfg)
    await resync(ctx.bot)
    await msg.reply_text(f"✅ /{name} dihapus.")


async def cmd_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    parts = msg.text.split()[1:]
    args = [p for p in parts if p.lower() != "baru"]
    force_new = len(args) != len(parts)
    if not args:
        await msg.reply_text(
            "Format: /post nama [@channel] [baru]\n"
            "• Tanpa @channel = pakai chat_id di config\n"
            "• Kalau sudah pernah diposting, pesan lama di-update. Tambah 'baru' buat kirim pesan baru.\n"
            "• Bot harus admin di channel itu (izin Post & Edit Messages).")
        return
    name = args[0].lstrip("/").lower()
    cfg = load_config()
    if name not in cfg.get("commands", {}):
        await msg.reply_text("❌ Command nggak ketemu.")
        return
    target = args[1] if len(args) > 1 else str(cfg.get("chat_id") or "")
    if not target:
        await msg.reply_text("❌ Tulis targetnya: /post nama @channel (atau isi chat_id di config).")
        return
    try:
        status = await publish(ctx.bot, name, target, force_new)
        await msg.reply_text(f"✅ {status}")
    except Exception as e:
        await msg.reply_text(f"❌ Gagal kirim: {e}")


ADMIN_CMDS = {
    "admin": cmd_admin,
    "inlinekeyboard": cmd_inlinekeyboard,
    "edit": cmd_edit,
    "addcmd": cmd_addcmd,
    "delcmd": cmd_delcmd,
    "post": cmd_post,
    "batal": cmd_batal,
}


# ------------------------------------------------------------- dispatcher ---
async def on_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    head = msg.text.split(None, 1)[0]
    cmd, _, target = head[1:].partition("@")
    cmd = cmd.lower()
    if target and target.lower() != (ctx.bot.username or "").lower():
        return  # ditujukan ke bot lain

    ctx.user_data.pop("await", None)  # command baru = batalin input yang ditunggu

    if cmd in ADMIN_CMDS:  # selalu cek di sini, bukan cuma lewat menu
        if msg.chat.type != "private":
            return
        if not is_admin(update.effective_user.id):
            await msg.reply_text("⛔ Khusus admin.")
            return
        await ADMIN_CMDS[cmd](update, ctx)
    elif cmd in USER_CMDS:
        await USER_CMDS[cmd](update, ctx)
    else:
        entry = load_config().get("commands", {}).get(cmd)
        if entry:
            admin = msg.chat.type == "private" and is_admin(update.effective_user.id)
            await send_custom(ctx.bot, msg.chat_id, entry, update.effective_user, cmd, admin)


# ------------------------------------------------------------------- main ---
def main():
    token = common.get_token()
    app = (ApplicationBuilder().token(token)
           .request(make_request(30))
           .get_updates_request(make_request(40))
           .post_init(lambda a: resync(a.bot))
           .build())
    app.add_handler(MessageHandler(filters.COMMAND, on_command))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, on_text))
    app.add_error_handler(on_error)
    if not common.get_admin_ids():
        log.warning('admin_ids kosong. Isi: python Src/manage.py add-admin <ID> (cek ID lewat /id)')
    log.info("Bot jalan...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__ser.id)  .build(