# InlineKeyboard

A simple Telegram bot for creating commands with text and link buttons (inline keyboards),
such as a `/menu` that shows a grid of bots or Mini Apps. Everything is managed **directly from
Telegram** or from the terminal (Termux) and stored in `Config/config.json`.

Messages already posted to a channel or group **keep working without the bot running** (link
buttons don't need the bot). Start the bot only when you want to change something, and the
posted messages are updated automatically.

## Features

- `/start` greets the user, then shows the menu (the `menu` command, configurable via `start_menu`)
- Admin-created commands with text (HTML) and link buttons to websites, `t.me` links, and more
- In-Telegram editor: change the text, add/remove buttons, set buttons per row, delete the command
- **⚡ Quick add**: send `Name | link` (multiple lines allowed), buttons are laid out automatically
- Admins who run a custom command (e.g. `/menu`) in private chat get a **⚙️ Edit** button
- `/post` publishes to a channel or group, and posting again **updates the existing message**
- Every edit in the editor automatically updates messages already posted to channels
- Terminal manager (`manage.py`): token, admins, manage buttons (add, delete, edit, move), post to channel
- The `/` command menu in Telegram syncs automatically (admins get the full menu)
- `/id` shows your User ID and Chat ID, tap to copy

## Structure

```
InlineKeyboard/
├── Src/
│   ├── bot.py        Telegram bot
│   ├── manage.py     terminal setup & management
│   └── common.py     shared config and helpers
├── Config/
│   ├── config.example.json   example config
│   └── config.json           created locally, NOT committed (contains the token)
├── requirements.txt
└── README.md
```

## Installation

```bash
git clone https://github.com/sushitrsh/InlineKeyboard.git
cd InlineKeyboard
pip install -r requirements.txt
python Src/manage.py token <TOKEN_FROM_BOTFATHER>
```

On Termux, if Python isn't installed yet: `pkg install python git`.

## Setup

1. Start the bot: `python Src/bot.py`
2. Open a private chat with the bot, send `/id`, and tap your User ID to copy it
3. Register yourself as admin: `python Src/manage.py add-admin <ID>`, then restart the bot

You can also do all of this from the interactive menu: `python Src/manage.py`.

## Usage in Telegram (admin, private chat)

| Command | What it does |
|---|---|
| `/inlinekeyboard name` | Create a new command and open its editor |
| `/edit [name]` | Open the editor for a command |
| `/addcmd name text` | Create a plain text command |
| `/delcmd name` | Delete a command |
| `/post name [@channel] [new]` | Post to a channel; posting again updates the old message, `new` forces a new message |
| `/batal` | Cancel the input the bot is waiting for |

Example: create a full `/menu` in a single message:

```
/inlinekeyboard menu
LIST AIRDROP BOT
Monkey Coast=https://t.me/MonkeyBot/app ; Dogs=https://t.me/DogsBot/app
SeedCoin=https://t.me/SeedBot/app
```

A line containing `Text=link` becomes one row of buttons (separate buttons with `;`). Any other
line becomes the message text. The text may use HTML (`<b>`, `<i>`, `<a href>`), and
`{first_name}` / `{user_id}` are replaced with the user's details.

In the editor, **⚡ Cepat** (quick add) accepts one button per line:

```
Monkey Coast | https://t.me/MonkeyBot/app
Dogs | https://t.me/DogsBot/app
```

The **🔢** button cycles the number of buttons per row (1 → 2 → 3 → 4).

## Usage in the terminal

```bash
python Src/manage.py                      # interactive menu
python Src/manage.py token <TOKEN>
python Src/manage.py add-admin <ID>
python Src/manage.py chat @yourchannel    # default target for /post
python Src/manage.py post menu            # post / update /menu in the channel
python Src/manage.py post menu --new      # force a new message
python Src/manage.py import bots.json     # import an old-format list as /menu
python Src/manage.py list                 # show a config summary
```

The **Manage commands & buttons** menu lets you add, delete (several at once: `2,4`), edit, move,
change the text, and set buttons per row. When you finish, `manage.py` offers to update the
message in your channel.

## Posting to a channel

1. Make the bot an admin of the channel (*Post Messages* and *Edit Messages* permissions)
2. Run `/post menu @yourchannel` or `python Src/manage.py post menu`, then pin the message
3. After that you can stop the bot, the buttons keep working. To change the list, start the bot,
   edit via ⚙️ Edit, and the channel message updates by itself

## Configuration

`Config/config.json`:

| Key | Description |
|---|---|
| `token` | Bot token from [@BotFather](https://t.me/BotFather) |
| `admin_ids` | List of admin User IDs |
| `chat_id` | Default posting target (`@channel` or `-100...`) |
| `start_text` | Greeting sent by `/start` |
| `start_menu` | Command shown after `/start` (default `menu`, set to `""` to disable) |
| `commands` | Custom commands (`text`, `per_row`, `buttons`) |
| `posts` | Tracked automatically: messages already posted to channels |

You can also use the `TOKEN` and `ADMINS` (comma-separated) environment variables, handy for
Codespaces or a server.

## Notes

- Admin commands only work in a private chat with an admin. Editor buttons are rejected for non-admins.
- If the bot is slow or the connection drops often on mobile data, run
  `NET_TWEAKS=1 python Src/bot.py` (forces IPv4 and disables keep-alive). Short network errors are retried automatically.
- On Termux, enable the wakelock (`termux-wake-lock`) and set Termux battery usage to *Unrestricted*.
  If the bot gets killed after changing system settings, reopen Termux.
- Old configs that still have a `list` command are migrated to `menu` automatically.
- Token leaked? Revoke it via @BotFather → `/mybots` → pick the bot → *API Token* → *Revoke current token*.
