"""Menu input di terminal buat ngatur daftar bot (tambah, hapus, edit, dll)."""
import common
import post

MENU = """
=== MANAGER LIST BOT ===
1. Lihat daftar
2. Tambah
3. Hapus
4. Edit
5. Ubah urutan
6. Judul & susunan
7. Pengaturan bot (token / admin / chat_id)
8. Kirim / update pesan ke channel
0. Keluar
"""


def show(d):
    print(f"\nJudul: {d['title']} | Per baris: {d['per_row']}")
    if not d["items"]:
        print("(kosong)")
    for i, it in enumerate(d["items"], 1):
        print(f"{i}. {it['name']} -> {it['link']}")


def add(d):
    while True:
        name = input("Nama tombol (kosong = selesai): ").strip()
        if not name:
            break
        link = input("Link: ").strip()
        if not common.valid_link(link):
            print("Link harus diawali http:// atau https://")
            continue
        d["items"].append({"name": name, "link": link})
        common.save_bots(d)
        print(f"+ {name} ditambah")


def delete(d):
    show(d)
    raw = input("Nomor yang dihapus (pisah koma, misal 2,4): ").strip()
    try:
        idx = sorted({int(x) for x in raw.split(",")}, reverse=True)
        if any(i < 1 or i > len(d["items"]) for i in idx):
            raise IndexError
        for i in idx:
            print(f"- {d['items'].pop(i - 1)['name']} dihapus")
        common.save_bots(d)
    except (ValueError, IndexError):
        print("Input nggak valid, batal.")


def edit(d):
    show(d)
    try:
        i = int(input("Nomor yang diedit: ")) - 1
        if i < 0:
            raise IndexError
        it = d["items"][i]
    except (ValueError, IndexError):
        print("Nomor nggak valid.")
        return
    it["name"] = input(f"Nama baru [{it['name']}]: ").strip() or it["name"]
    link = input(f"Link baru [{it['link']}]: ").strip()
    if link:
        if common.valid_link(link):
            it["link"] = link
        else:
            print("Link nggak valid, link lama dipertahankan.")
    common.save_bots(d)


def move(d):
    show(d)
    try:
        a = int(input("Pindah nomor: ")) - 1
        b = int(input("Ke posisi: ")) - 1
        if a < 0 or b < 0 or a >= len(d["items"]) or b >= len(d["items"]):
            raise IndexError
        d["items"].insert(b, d["items"].pop(a))
        common.save_bots(d)
    except (ValueError, IndexError):
        print("Input nggak valid.")


def settings(d):
    t = input(f"Judul pesan [{d['title']}]: ").strip()
    p = input(f"Tombol per baris [{d['per_row']}]: ").strip()
    if t:
        d["title"] = t
    if p.isdigit() and 1 <= int(p) <= 8:
        d["per_row"] = int(p)
    common.save_bots(d)


def bot_settings():
    while True:
        cfg = common.load_config()
        has_token = cfg.get("token") not in (None, "", common.TOKEN_PLACEHOLDER)
        print("\n--- Pengaturan bot ---")
        print(f"Token   : {'terisi' if has_token else 'belum diisi'}")
        print(f"Admin   : {cfg.get('admins', [])}")
        print(f"Chat ID : {cfg.get('chat_id', '(belum diisi)')}")
        print("1. Set token\n2. Set admin ID (pisah koma)\n3. Set chat_id tujuan post\n0. Kembali")
        c = input("Pilih: ").strip()
        if c == "1":
            t = input("Token bot: ").strip()
            if ":" in t:
                cfg["token"] = t
                common.save_config(cfg)
                print("Token disimpan.")
            else:
                print("Format token nggak valid.")
        elif c == "2":
            raw = input("ID admin (cek lewat /id di bot): ").strip()
            try:
                cfg["admins"] = [int(x) for x in raw.split(",") if x.strip()]
                common.save_config(cfg)
                print("Admin disimpan.")
            except ValueError:
                print("ID harus angka.")
        elif c == "3":
            raw = input(
                "Tujuan (ID, @username, nama, atau tujuan/thread_id): "
            ).strip()

            try:
                if not raw:
                    raise ValueError("Tujuan tidak boleh kosong")

                if "/" in raw:
                    chat_raw, thread_raw = raw.rsplit("/", 1)
                    chat_raw = chat_raw.strip()
                    thread_raw = thread_raw.strip()

                    if not chat_raw or not thread_raw.isdigit():
                        raise ValueError(
                            "Format thread harus tujuan/angka"
                        )

                    if int(thread_raw) < 1:
                        raise ValueError("Thread ID harus positif")

                    if chat_raw.lstrip("-").isdigit():
                        chat_value = int(chat_raw)
                        if chat_value >= 0:
                            raise ValueError(
                                "ID grup numerik harus negatif"
                            )
                    else:
                        chat_value = (
                            chat_raw if chat_raw.startswith("@")
                            else "@" + chat_raw
                        )

                    cfg["chat_id"] = chat_value
                    cfg["message_thread_id"] = int(thread_raw)

                else:
                    if raw.lstrip("-").isdigit():
                        chat_value = int(raw)
                        if chat_value >= 0:
                            raise ValueError(
                                "ID grup numerik harus negatif"
                            )
                    else:
                        chat_value = (
                            raw if raw.startswith("@")
                            else "@" + raw
                        )

                    cfg["chat_id"] = chat_value
                    cfg.pop("message_thread_id", None)

                common.save_config(cfg)
                print("Tujuan berhasil disimpan.")
                print(f"Chat ID : {cfg['chat_id']}")
                print(
                    "Thread  : "
                    f"{cfg.get('message_thread_id', '(tidak disetel)')}"
                )

            except ValueError as e:
                print(f"Input tidak valid: {e}")
        elif c == "0":
            return


def publish():
    try:
        print(post.run())
    except (RuntimeError, SystemExit) as e:
        print(e)


def main():
    actions = {"1": show, "2": add, "3": delete, "4": edit, "5": move, "6": settings}
    while True:
        d = common.load_bots()
        print(MENU)
        c = input("Pilih: ").strip()
        if c in actions:
            actions[c](d)
        elif c == "7":
            bot_settings()
        elif c == "8":
            publish()
        elif c == "0":
            break


if __name__ == "__main__":
    main()
