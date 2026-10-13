"""Bot Telegram: /list menampilkan tombol daftar bot, admin bisa tambah/hapus.

Jalankan hanya saat mau ngubah daftar. Pesan daftar yang sudah diposting
(lihat post.py) otomatis ikut ke-update lewat state.json.
"""
import asyncio
import os
import traceback

import httpx
from telegram import (ForceReply, InlineKeyboardButton as Btn,
                      InlineKeyboardMarkup as Markup, Update)
from telegram.ext import (ApplicationBuilder, CallbackQueryHandler,
                          CommandHandler, ContextTypes, MessageHandler, filters)
from telegram.error import NetworkError, TimedOut
from telegram.request import HTTPXRequest

import common

ADMINS = common.get_admins()
_tasks = set()


def make_request(read_timeout):
    kw = {}
    if os.environ.get("NET_TWEAKS") == "1":
        # Opsional: paksa IPv4 dan matiin keep-alive
        kw["httpx_kwargs"] = {"transport": httpx.AsyncHTTPTransport(
            local_address="0.0.0.0", retries=2,
            limits=httpx.Limits(max_keepalive_connections=0))}
    return HTTPXRequest(connect_timeout=20, read_timeout=read_timeout,
                        write_timeout=30, pool_timeout=30, **kw)


def fire(coro):
    """Jalanin coroutine di latar belakang tanpa nunggu hasilnya."""
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def safe_answer(q):
    try:
        await q.answer()
    except Exception:
        pass  # klik basi / timeout, nggak masalah


def is_admin(update: Update):
    user = update.effective_user
    return bool(user and user.id in ADMINS)


def list_markup(d, admin=False):
    btns = [Btn(i["name"], url=i["link"]) for i in d["items"]]
    rows = common.chunk(btns, d["per_row"])
    if admin:
        rows.append([Btn("➕ Tambah", callback_data="add"),
                     Btn("🗑 Hapus", callback_data="del")])
    return Markup(rows)


def delete_markup(d):
    rows = [[Btn(f"❌ {it['name']}", callback_data=f"rm:{i}")]
            for i, it in enumerate(d["items"])]
    rows.append([Btn("⬅️ Batal", callback_data="back")])
    return Markup(rows)


async def refresh(bot):
    """Update pesan daftar yang sudah diposting lewat post.py."""
    d = common.load_bots()
    for chat, mid in common.read_json(common.STATE_FILE, {}).items():
        try:
            await bot.edit_message_text(
                chat_id=chat, message_id=mid, text=d["title"],
                reply_markup=list_markup(d, False))
        except Exception as e:
            print("Refresh gagal:", e)


async def id_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"ID lo: <code>{update.effective_user.id}</code>", parse_mode="HTML")


async def list_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = common.load_bots()
    await update.message.reply_text(
        d["title"], reply_markup=list_markup(d, is_admin(update)))


async def on_click(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(update):
        await safe_answer_alert(q, "Khusus admin.")
        return

    d = common.load_bots()
    if q.data == "del" and not d["items"]:
        await safe_answer_alert(q, "Daftar masih kosong.")
        return
    fire(safe_answer(q))

    if q.data == "add":
        ctx.user_data["await_add"] = True
        await q.message.reply_text(
            "Balas pesan ini dengan format:\nNama | link\n\n"
            "Contoh:\nDogs | https://t.me/DogsBot/app\nWeb | https://example.com\n\n"
            "Ketik batal buat cancel.",
            reply_markup=ForceReply())

    elif q.data == "del":
        await q.edit_message_reply_markup(delete_markup(d))

    elif q.data == "back":
        await q.edit_message_reply_markup(list_markup(d, True))

    elif q.data.startswith("rm:"):
        try:
            i = int(q.data[3:])
        except ValueError:
            return
        if 0 <= i < len(d["items"]):
            d["items"].pop(i)
            common.save_bots(d)
            await refresh(ctx.bot)
        await q.edit_message_reply_markup(
            delete_markup(d) if d["items"] else list_markup(d, True))


async def safe_answer_alert(q, text):
    try:
        await q.answer(text, show_alert=True)
    except Exception:
        pass


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.user_data.get("await_add") or not is_admin(update):
        return
    text = update.message.text.strip()
    if text.lower() == "batal":
        ctx.user_data["await_add"] = False
        await update.message.reply_text("Dibatalin.")
        return
    if "|" not in text:
        await update.message.reply_text("Format salah. Pakai: Nama | link")
        return
    name, link = [x.strip() for x in text.split("|", 1)]
    if not name or not common.valid_link(link):
        await update.message.reply_text(
            "Nama kosong atau link nggak valid (harus diawali http:// atau https://). Coba lagi.")
        return
    d = common.load_bots()
    d["items"].append({"name": name, "link": link})
    common.save_bots(d)
    ctx.user_data["await_add"] = False
    await refresh(ctx.bot)
    await update.message.reply_text(
        f"✅ {name} ditambah.", reply_markup=list_markup(d, True))


async def on_error(update, ctx: ContextTypes.DEFAULT_TYPE):
    err = ctx.error
    if isinstance(err, (NetworkError, TimedOut)):
        print(f"Jaringan putus sesaat ({type(err).__name__}), nyoba lagi...")
        return
    print("Error:", repr(err))
    traceback.print_exception(err)


def main():
    builder = ApplicationBuilder().token(common.get_token())
    if os.environ.get("SIMPLE") != "1":
        builder = (builder.request(make_request(30))
                   .get_updates_request(make_request(40))
                   .concurrent_updates(True))
    app = builder.build()
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CallbackQueryHandler(on_click))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    if not ADMINS:
        print('Peringatan: "admins" kosong, tombol Tambah/Hapus nggak bisa dipakai.')
    app.run_polling(drop_pending_updates=os.environ.get("SIMPLE") != "1")


if __name__ == "__main__":
    main()
