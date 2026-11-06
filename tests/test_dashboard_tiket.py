"""Uji kotak masuk tiket dari dashboard web + editor kolom formulir visual."""

from __future__ import annotations

import socket
import time

import aiohttp

import dashboard_pesan as dp
import dashboard_tiket as dt
import dashboard_ui as ui
import tickets
import web_dashboard

GID = 1234
TID = 7001


# ==============================================================================
# PERKAKAS
# ==============================================================================
class _Guild:
    def __init__(self, gid=GID, nama="Server Uji"):
        self.id = gid
        self.name = nama
        self.member_count = 3
        self.channels = []
        self.roles = []


class _Thread:
    """Thread tiket palsu: mencatat pesan & perubahan status."""

    def __init__(self, tid=TID, gid=GID):
        self.id = tid
        self.name = "tiket-0001"
        self.guild = type("G", (), {"id": gid})()
        self.terkirim: list[dict] = []
        self.diedit: list[dict] = []

    async def send(self, **kwargs):
        self.terkirim.append(kwargs)
        return type("M", (), {"id": len(self.terkirim)})()

    async def edit(self, **kwargs):
        self.diedit.append(kwargs)
        return self

    async def history(self, **_kwargs):
        async def _kosong():
            if False:  # pragma: no cover - generator kosong
                yield None

        return _kosong()


class _Bot:
    def __init__(self, guilds=(), channel=None):
        self.guilds = list(guilds)
        self.latency = 0.01
        self.user = type("U", (), {"id": 999, "name": "BotUji"})()
        self._channel = channel

    def get_guild(self, gid):
        for g in self.guilds:
            if g.id == int(gid):
                return g
        return None

    def get_channel(self, cid):
        if self._channel is not None and int(cid) == int(self._channel.id):
            return self._channel
        return None


def _siapkan_tiket(status="terbuka", *, gid=GID, tid=TID, umur_jam=2.0, topic="bantuan akun"):
    """Isi `tickets.tickets` dengan satu tiket & matikan tulis disk."""
    sekarang = time.time()
    tickets.tickets.clear()
    data = {
        "thread_id": tid,
        "guild_id": gid,
        "user_id": 33,
        "number": 1,
        "status": status,
        "topic": topic,
        "created_at": sekarang - umur_jam * 3600,
        "claimed_by": 22 if status == "diklaim" else None,
        "closed_by": None,
        "closed_at": 0.0,
        "added_users": [],
        "first_response_at": 0.0,
        "first_response_by": None,
        "last_activity": sekarang - 600,
        "sla_alerted": False,
        "rating": 0,
        "rated_at": 0.0,
        "closed_reason": "",
    }
    tickets.tickets[tid] = data
    return data


async def _simpan_palsu():
    return None


# ==============================================================================
# collect_tiket
# ==============================================================================
def test_collect_tiket_ringkas_aktif(monkeypatch):
    monkeypatch.setattr(tickets, "save_tickets_to_disk", _simpan_palsu, raising=False)
    _siapkan_tiket(umur_jam=5)
    data = dt.collect_tiket(GID)

    assert data["guild"] == GID
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["nomor"] == "#0001"
    assert item["status"] == "terbuka"
    assert item["status_label"] == "🟢 Terbuka"
    assert item["pemilik"] == "33"
    assert item["topik"] == "bantuan akun"
    assert item["umur"] == "5 jam"
    assert item["diam"] == "10 mnt"
    assert item["diklaim"] == "" and item["sla"] is False
    assert data["statistik"]["aktif"] == 1
    assert data["statistik"]["diklaim"] == 0


def test_collect_tiket_menandai_lewat_sla(monkeypatch):
    monkeypatch.setattr(tickets, "save_tickets_to_disk", _simpan_palsu, raising=False)
    monkeypatch.setattr(
        tickets, "get_ticket_config", lambda gid: {"enabled": True, "sla_jam": 1, "max_open": 3},
        raising=False,
    )
    _siapkan_tiket(umur_jam=4)

    data = dt.collect_tiket(GID)
    assert data["items"][0]["sla"] is True
    assert data["items"][0]["sla_jam"] == 1
    assert data["statistik"]["lewat_sla"] == 1
    assert data["statistik"]["aktifkan"] is True


def test_collect_tiket_melewati_yang_selesai_dan_server_lain(monkeypatch):
    monkeypatch.setattr(tickets, "save_tickets_to_disk", _simpan_palsu, raising=False)
    _siapkan_tiket(status="selesai")
    tickets.tickets[8002] = dict(tickets.tickets[TID], thread_id=8002, guild_id=9999, status="terbuka")

    data = dt.collect_tiket(GID)
    assert data["items"] == []
    assert data["statistik"]["aktif"] == 0


def test_collect_tiket_membatasi_jumlah(monkeypatch):
    monkeypatch.setattr(tickets, "save_tickets_to_disk", _simpan_palsu, raising=False)
    now = time.time()
    tickets.tickets.clear()
    for index in range(6):
        tickets.tickets[7100 + index] = {
            "thread_id": 7100 + index,
            "guild_id": GID,
            "user_id": 33,
            "number": index + 1,
            "status": "terbuka",
            "topic": "t",
            "created_at": now - index * 60,
            "last_activity": now - index * 60,
        }
    assert len(dt.collect_tiket(GID, limit=2)["items"]) == 2


# ==============================================================================
# render_tiket_block
# ==============================================================================
def _contoh_paket(**ubah):
    paket = {
        "guild": GID,
        "items": [
            {
                "id": str(TID),
                "nomor": "#0001",
                "pemilik": "33",
                "topik": "bantuan akun",
                "status": "terbuka",
                "status_label": "🟢 Terbuka",
                "diklaim": "",
                "umur": "2 jam",
                "diam": "10 mnt",
                "sla": True,
                "sla_jam": 1,
            }
        ],
        "statistik": {"aktif": 1, "diklaim": 0, "lewat_sla": 1, "rating": "4.5 ★ (2)", "aktifkan": True},
    }
    paket.update(ubah)
    return paket


def test_render_tiket_block_memuat_form_balas_dan_tutup():
    html = ui.render_tiket_block(GID, _contoh_paket(), "tok")

    assert "Aktif: <b>1</b>" in html
    assert "lewat SLA: 1" in html
    assert "4.5 ★ (2)" in html
    assert 'class="tiket-baris"' in html
    assert "lewat SLA</span>" in html
    assert "#0001" in html and "bantuan akun" in html and "10 mnt" in html
    assert 'action="/api/tiket"' in html
    assert 'value="balas:7001"' in html
    assert 'value="tutup:7001"' in html
    assert 'value="tok"' in html and 'value="1234"' in html
    assert 'class="danger"' in html


def test_render_tiket_block_kosong_dan_nonaktif():
    html = ui.render_tiket_block(GID, {"items": [], "statistik": {"aktifkan": False}}, "tok")
    assert "Tidak ada tiket aktif" in html
    assert "Sistem tiket nonaktif" in html
    assert "/api/tiket" not in html


def test_render_tiket_block_escape_html():
    paket = _contoh_paket()
    paket["items"][0]["topik"] = "<script>alert(1)</script>"
    html = ui.render_tiket_block(GID, paket, "tok")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ==============================================================================
# kolom_dari_baris (editor kolom formulir visual)
# ==============================================================================
def test_kolom_dari_baris_lengkap():
    kolom = dp.kolom_dari_baris(
        {
            "kolom_label_1": "Nama",
            "kolom_jenis_1": "pendek",
            "kolom_wajib_1": "on",
            "kolom_label_2": "Alasan",
            "kolom_jenis_2": "panjang",
            "kolom_wajib_2": "on",
            "kolom_label_3": "Kota",
            "kolom_jenis_3": "pendek",
        }
    )
    assert kolom == "Nama | Alasan:panjang | Kota?"


def test_kolom_dari_baris_kosong_dan_sanitasi():
    assert dp.kolom_dari_baris({}) == ""
    assert dp.kolom_dari_baris({"kolom_label_1": "   "}) == ""
    # Karakter pipa diganti agar tidak memecah sintaks modal_forms
    assert dp.kolom_dari_baris({"kolom_label_1": "A|B", "kolom_wajib_1": "on"}) == "A/B"


def test_kolom_dari_baris_dibatasi_lima():
    data = {f"kolom_label_{n}": f"K{n}" for n in range(1, 9)}
    # tanpa centang "wajib" setiap kolom menjadi opsional
    assert dp.kolom_dari_baris(data) == "K1? | K2? | K3? | K4? | K5?"


def test_form_formulir_punya_baris_visual_dan_mode_lanjutan():
    html = ui.render_buat_block(_Bot([_Guild()]), GID, "tok")
    assert 'class="kolom-formulir"' in html
    assert html.count('class="baris-kolom"') == 5
    assert 'name="kolom_label_1"' in html and 'name="kolom_label_5"' in html
    assert 'name="kolom_jenis_1"' in html and 'value="panjang"' in html
    assert 'name="kolom_wajib_5"' in html
    assert "<details>" in html and 'name="kolom"' in html      # mode lanjutan tetap ada


# ==============================================================================
# balas / tutup (level modul)
# ==============================================================================
async def test_balas_mengirim_ke_thread(monkeypatch):
    monkeypatch.setattr(tickets, "save_tickets_to_disk", _simpan_palsu, raising=False)
    _siapkan_tiket()
    thread = _Thread()
    bot = _Bot([_Guild()], channel=thread)

    ok, pesan = await dt.balas(bot, GID, TID, "  Halo, kami cek dulu ya  ")
    assert ok is True
    assert "Balasan terkirim ke tiket #0001" in pesan
    assert thread.terkirim[0]["content"] == "Halo, kami cek dulu ya"
    assert tickets.tickets[TID]["first_response_at"] > 0       # SLA tercatat


async def test_balas_menolak_teks_kosong_dan_tiket_selesai(monkeypatch):
    monkeypatch.setattr(tickets, "save_tickets_to_disk", _simpan_palsu, raising=False)
    _siapkan_tiket()
    bot = _Bot([_Guild()], channel=_Thread())

    ok, pesan = await dt.balas(bot, GID, TID, "   ")
    assert ok is False and "tidak boleh kosong" in pesan

    tickets.tickets[TID]["status"] = "selesai"
    ok, pesan = await dt.balas(bot, GID, TID, "Halo")
    assert ok is False and "sudah ditutup" in pesan


async def test_balas_menolak_tiket_server_lain(monkeypatch):
    monkeypatch.setattr(tickets, "save_tickets_to_disk", _simpan_palsu, raising=False)
    _siapkan_tiket(gid=GID)
    ok, pesan = await dt.balas(_Bot([_Guild()], channel=_Thread()), 5555, TID, "Halo")
    assert ok is False and "tidak ditemukan" in pesan


async def test_balas_lewat_webhook_bila_identitas_diisi(monkeypatch):
    monkeypatch.setattr(tickets, "save_tickets_to_disk", _simpan_palsu, raising=False)
    _siapkan_tiket()
    dipanggil = {}

    async def kirim_sebagai(channel, *, nama, isi):
        dipanggil["nama"] = nama
        dipanggil["isi"] = isi
        return True, "ok"

    import webhook_identity

    monkeypatch.setattr(webhook_identity, "kirim_sebagai", kirim_sebagai)
    bot = _Bot([_Guild()], channel=_Thread())

    ok, pesan = await dt.balas(bot, GID, TID, "Halo", identitas="Tim Bantuan")
    assert ok is True and "terkirim" in pesan
    assert dipanggil == {"nama": "Tim Bantuan", "isi": "Halo"}


async def test_tutup_mengunci_dan_mengarsip_thread(monkeypatch):
    monkeypatch.setattr(tickets, "save_tickets_to_disk", _simpan_palsu, raising=False)
    _siapkan_tiket()

    async def _pesan(thread):
        return []

    monkeypatch.setattr(tickets, "collect_thread_messages", _pesan, raising=False)
    monkeypatch.setattr(tickets, "build_transcript", lambda data, pesan: ("isi", "t.txt"), raising=False)

    async def _kirim(bot, data, teks, nama):
        return False

    monkeypatch.setattr(tickets, "send_transcript", _kirim, raising=False)
    thread = _Thread()
    bot = _Bot([_Guild()], channel=thread)

    ok, pesan = await dt.tutup(bot, GID, TID)
    assert ok is True
    assert "#0001" in pesan and "ditutup" in pesan
    assert tickets.tickets[TID]["status"] == "selesai"
    assert tickets.tickets[TID]["closed_reason"] == "dashboard"
    assert thread.diedit[0]["locked"] is True and thread.diedit[0]["archived"] is True
    assert thread.diedit[0]["name"] == "tiket-0001-selesai"


async def test_tutup_menolak_tiket_sudah_selesai(monkeypatch):
    monkeypatch.setattr(tickets, "save_tickets_to_disk", _simpan_palsu, raising=False)
    _siapkan_tiket(status="selesai")
    ok, pesan = await dt.tutup(_Bot([_Guild()], channel=_Thread()), GID, TID)
    assert ok is False and "sudah ditutup" in pesan


# ==============================================================================
# RUTE HTTP /api/tiket
# ==============================================================================
async def _jalankan(monkeypatch, bot, fn):
    import dashboard_unggah as du

    monkeypatch.setattr(du, "UPLOAD_DIR", __import__("pathlib").Path("/tmp/uji-tiket-uploads"))
    monkeypatch.setattr(web_dashboard, "DASHBOARD_HOST", "127.0.0.1")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(web_dashboard, "DASHBOARD_PORT", port)
    monkeypatch.setattr(web_dashboard, "DASHBOARD_TOKEN", "tok-tiket")

    assert await web_dashboard.start_dashboard(bot) is True
    try:
        async with aiohttp.ClientSession() as session:
            return await fn(session, f"http://127.0.0.1:{port}")
    finally:
        await web_dashboard.stop_dashboard()


async def test_http_tiket_daftar_dan_izin(monkeypatch):
    monkeypatch.setattr(tickets, "save_tickets_to_disk", _simpan_palsu, raising=False)
    _siapkan_tiket()
    bot = _Bot([_Guild()], channel=_Thread())

    async def skenario(session, base):
        async with session.get(f"{base}/api/tiket?guild={GID}") as resp:
            assert resp.status == 401
        async with session.get(
            f"{base}/api/tiket?guild={GID}", headers={"X-Dashboard-Token": "tok-tiket"}
        ) as resp:
            data = await resp.json()
            assert resp.status == 200
            assert data["items"][0]["nomor"] == "#0001"

        # Panel tiket tampil di halaman /tiket
        async with session.get(f"{base}/tiket?token=tok-tiket&guild={GID}") as resp:
            body = await resp.text()
            assert resp.status == 200
            assert "Kotak masuk tiket" in body and "balas:7001" in body

    await _jalankan(monkeypatch, bot, skenario)


async def test_http_tiket_balas_json_dan_html(monkeypatch):
    monkeypatch.setattr(tickets, "save_tickets_to_disk", _simpan_palsu, raising=False)
    _siapkan_tiket()
    thread = _Thread()
    bot = _Bot([_Guild()], channel=thread)

    async def skenario(session, base):
        async with session.post(
            f"{base}/api/tiket",
            json={"token": "tok-tiket", "guild": str(GID), "action": f"balas:{TID}", "teks": "Halo dari web"},
        ) as resp:
            data = await resp.json()
            assert resp.status == 200 and data["ok"] is True
            assert "terkirim" in data["message"]
        assert thread.terkirim[-1]["content"] == "Halo dari web"

        async with session.post(
            f"{base}/api/tiket",
            data={"token": "tok-tiket", "guild": str(GID), "action": f"balas:{TID}", "teks": ""},
        ) as resp:
            body = await resp.text()
            # gagal → kembali ke halaman Tiket dengan kotak ⚠️
            assert resp.status == 200 and "ok=0" in str(resp.url)
            assert "tidak boleh kosong" in body and 'class="flash galat"' in body

    await _jalankan(monkeypatch, bot, skenario)


async def test_http_tiket_tutup_dan_aksi_asing(monkeypatch):
    monkeypatch.setattr(tickets, "save_tickets_to_disk", _simpan_palsu, raising=False)
    _siapkan_tiket()

    async def _pesan(thread):
        return []

    monkeypatch.setattr(tickets, "collect_thread_messages", _pesan, raising=False)
    monkeypatch.setattr(tickets, "build_transcript", lambda data, pesan: ("isi", "t.txt"), raising=False)

    async def _kirim(bot, data, teks, nama):
        return False

    monkeypatch.setattr(tickets, "send_transcript", _kirim, raising=False)
    thread = _Thread()
    bot = _Bot([_Guild()], channel=thread)

    async def skenario(session, base):
        async with session.post(
            f"{base}/api/tiket",
            json={"token": "tok-tiket", "guild": str(GID), "action": "hapus:1"},
        ) as resp:
            data = await resp.json()
            assert resp.status == 400 and data["ok"] is False
            assert "tidak dikenal" in data["message"]

        async with session.post(
            f"{base}/api/tiket",
            data={"token": "tok-tiket", "guild": str(GID), "action": f"tutup:{TID}"},
        ) as resp:
            body = await resp.text()
            assert resp.status == 200 and "ditutup" in body
        assert tickets.tickets[TID]["status"] == "selesai"
        assert thread.diedit[0]["archived"] is True

    await _jalankan(monkeypatch, bot, skenario)
