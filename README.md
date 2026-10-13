# InlineKeyboard

Bot Telegram buat bikin command dengan teks dan tombol link (inline keyboard), contohnya `/menu`
yang nampilin daftar bot/Mini App sebagai grid tombol. Semuanya diatur **langsung dari Telegram**
atau dari terminal (Termux), dan disimpan di `Config/config.json`.

Pesan yang sudah diposting ke channel/grup **tetap jalan tanpa bot hidup** (tombol link tidak butuh bot).
Jalankan bot hanya saat mau ngubah daftar, pesan di channel ikut ke-update otomatis.

## Fitur

- `/start` nyapa user lalu otomatis nampilin menu (command `menu`, bisa diganti lewat `start_menu` di config)
- Command buatan admin dengan teks (HTML) + tombol link ke website, `t.me`, dll
- Editor di Telegram: ganti teks, tambah/hapus tombol, atur jumlah tombol per baris, hapus command
- **⚡ Cepat**: kirim `Nama | link` (boleh banyak baris), tombol otomatis disusun sesuai tombol per baris
- Admin yang jalanin command buatan (mis. `/menu`) di chat pribadi dapat tombol **⚙️ Edit**
- `/post` kirim ke channel/grup, pengiriman kedua meng-**update pesan lama** (bukan pesan baru)
- Setiap edit di editor otomatis ikut meng-update pesan yang sudah diposting
- Menu terminal `manage.py`: token, admin, kelola tombol (tambah, hapus, edit, pindah), posting ke channel
- Menu `/` di Telegram otomatis ikut command buatan (admin dapat menu lengkap)
- `/id` nampilin User ID dan Chat ID yang bisa disalin dengan sekali tap

## Struktur

```
InlineKeyboard/
├── Src/
│   ├── bot.py        bot Telegram
│   ├── manage.py     setup & kelola dari terminal
│   └── common.py     config dan helper bersama
├── Config/
│   ├── config.example.json   contoh config
│   └── config.json           dibuat lokal, TIDAK ikut ke GitHub (ada token)
├── requirements.txt
└── README.md
```

## Instalasi

```bash
git clone https://github.com/sushitrsh/InlineKeyboard.git
cd InlineKeyboard
pip install -r requirements.txt
python Src/manage.py token <TOKEN_DARI_BOTFATHER>
```

Di Termux, kalau belum ada Python: `pkg install python git`.

## Setup

1. Jalanin bot: `python Src/bot.py`
2. Chat pribadi ke bot, kirim `/id`, tap angka User ID buat nyalin
3. Daftarin sebagai admin: `python Src/manage.py add-admin <ID>`, lalu restart bot

Alternatif: semua langkah di atas bisa lewat menu interaktif `python Src/manage.py`.

## Pemakaian di Telegram (admin, chat pribadi)

| Command | Fungsi |
|---|---|
| `/inlinekeyboard nama` | Bikin command baru dan langsung buka editornya |
| `/edit [nama]` | Buka editor command |
| `/addcmd nama teks` | Bikin command teks biasa |
| `/delcmd nama` | Hapus command |
| `/post nama [@channel] [baru]` | Kirim ke channel; kedua kalinya update pesan lama, `baru` = paksa pesan baru |
| `/batal` | Batalin input yang lagi ditunggu |

Contoh bikin `/menu` lengkap dalam satu pesan:

```
/inlinekeyboard menu
LIST AIRDROP BOT
Monkey Coast=https://t.me/MonkeyBot/app ; Dogs=https://t.me/DogsBot/app
SeedCoin=https://t.me/SeedBot/app
```

Baris berisi `Teks=link` jadi satu baris tombol (pisah tombol pakai `;`), baris lain jadi teks pesan.
Teks pesan boleh HTML (`<b>`, `<i>`, `<a href>`), dan `{first_name}` / `{user_id}` diganti nama user.

## Pemakaian di terminal

```bash
python Src/manage.py                      # menu interaktif
python Src/manage.py token <TOKEN>
python Src/manage.py add-admin <ID>
python Src/manage.py chat @namachannel    # tujuan default /post
python Src/manage.py post menu            # kirim / update /menu ke channel
python Src/manage.py post menu --new      # paksa pesan baru
python Src/manage.py import bots.json     # impor daftar format lama jadi /menu
python Src/manage.py list                 # lihat ringkasan config
```

Di menu **Kelola command & tombol** ada tambah, hapus (bisa banyak: `2,4`), edit, pindah urutan,
ganti teks, dan atur tombol per baris. Setelah selesai, manage.py nawarin update pesan di channel.

## Posting ke channel

1. Jadiin bot admin channel (izin *Post Messages* dan *Edit Messages*)
2. `/post menu @namachannel` atau `python Src/manage.py post menu`, lalu pin pesannya
3. Habis itu bot boleh dimatiin, tombol tetap jalan. Mau ngubah daftar: nyalain bot, edit lewat ⚙️ Edit,
   pesan di channel ke-update sendiri

## Konfigurasi

`Config/config.json`:

| Key | Isi |
|---|---|
| `token` | Token dari [@BotFather](https://t.me/BotFather) |
| `admin_ids` | Daftar User ID admin |
| `chat_id` | Tujuan default posting (`@channel` atau `-100...`) |
| `start_text` | Teks sapaan `/start` |
| `start_menu` | Command yang ditampilin setelah `/start` (default `menu`, kosongin buat nonaktif) |
| `commands` | Command buatan (teks, `per_row`, `buttons`) |
| `posts` | Dicatat otomatis: pesan yang sudah diposting ke channel |

Bisa juga lewat environment variable `TOKEN` dan `ADMINS` (pisah koma), berguna buat Codespaces atau server.

## Catatan

- Command admin hanya jalan di chat pribadi dengan admin. Tombol editor di grup/channel ditolak buat non-admin.
- Kalau respon bot lambat atau sering putus di jaringan HP, jalanin dengan `NET_TWEAKS=1 python Src/bot.py`
  (paksa IPv4, matiin keep-alive). Error jaringan sesaat otomatis dicoba ulang.
- Di Termux, nyalain wakelock (`termux-wake-lock`) dan set baterai Termux ke *Unrestricted*. Kalau bot ke-kill
  setelah ngubah setelan sistem, buka ulang Termux.
- Token bocor? Revoke lewat @BotFather → `/mybots` → pilih bot → *API Token* → *Revoke current token*.
