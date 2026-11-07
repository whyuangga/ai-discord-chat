"""Uji honeypot (channel jebakan): konfigurasi, eksekusi tindakan, & permukaan dashboard.

Prinsip yang dikunci di sini:
* default **lapor** — belum ada tindakan sampai Admin memilih yang lebih keras;
* **staf & bot selalu aman** (kecuali Admin mematikan *abaikan staf*);
* pesan hanya ditindak di channel jebakan yang **aktif**;
* simulasi dashboard (`akan_tertangkap`) **tidak** mengubah state.
"""

from __future__ import annotations

import pytest

import dashboard_uji
import dashboard_ui
import honeypot
import web_dashboard

GID = 9301


# ==============================================================================
# PERKAKAS
# ==============================================================================
@pytest.fixture(autouse=True)
def _bersihkan(monkeypatch):
    honeypot.reset_runtime_state()

    async def _tanpa_simpan():
        return None

    monkeypatch.setattr(honeypot, "save_honeypot_to_disk", _tanpa_simpan)
    yield
    honeypot.reset_runtime_state()


class _Izin:
    def __init__(self, **kwargs):
        self.administrator = kwargs.get("administrator", False)
        self.manage_messages = kwargs.get("manage_messages", False)
        self.manage_guild = kwargs.get("manage_guild", False)


class _Anggota:
    def __init__(self, uid: int = 501, *, bot: bool = False, izin: _Izin | None = None,
                 owner_id: int = 0, nama: str = "Warga"):
        self.id = uid
        self.bot = bot
        self.display_name = nama
        self.mention = f"<@{uid}>"
        self.guild_permissions = izin or _Izin()
        self.guild = type("G", (), {"id": GID, "owner_id": owner_id, "name": "Server Uji"})()
        self.timeout_calls: list = []
        self.kick_calls: list = []
        self.ban_calls: list = []

    async def timeout(self, durasi, reason: str = ""):
        self.timeout_calls.append((durasi, reason))

    async def kick(self, reason: str = ""):
        self.kick_calls.append(reason)

    async def ban(self, reason: str = ""):
        self.ban_calls.append(reason)


class _Kanal:
    def __init__(self, cid: int = 700):
        self.id = cid
        self.mention = f"<#{cid}>"
        self.guild = type("G", (), {"id": GID, "name": "Server Uji"})()
        self.kirim: list = []

    async def send(self, *args, **kwargs):
        self.kirim.append(kwargs)
        return None


class _Pesan:
    def __init__(self, author: _Anggota, channel: _Kanal, *, isi: str = "promo gratis"):
        self.content = isi
        self.author = author
        self.channel = channel
        self.guild = channel.guild
        self.deleted = False

    async def delete(self):
        self.deleted = True


def _siapkan(aksi: str = "lapor", **kwargs) -> dict:
    return honeypot.set_honeypot(GID, channel_ids=[700], aksi=aksi, **kwargs)


# ==============================================================================
# KONFIGURASI
# ==============================================================================
def test_default_nonaktif_dan_paling_aman():
    data = honeypot.status(GID)
    assert data["aktif"] is False
    assert data["channel_ids"] == []
    assert data["aksi"] == "lapor"
    assert data["abaikan_staf"] is True
    assert data["tangkap"] == 0
    assert data["batas_channel"] == honeypot.HONEYPOT_MAX_CHANNEL == 3
    # Belum ada setelan tersimpan sebelum diubah.
    assert honeypot.peek_config(GID)["channel_ids"] == []


def test_channel_dibatasi_tiga_dan_diduplikasi():
    cfg = honeypot.set_honeypot(GID, channel_ids=[555, 556, 555, 557, 558])
    assert cfg["channel_ids"] == [555, 556, 557]
    assert honeypot.status(GID)["aktif"] is True


def test_aksi_tidak_dikenal_diabaikan_dan_timeout_dijepit():
    honeypot.set_honeypot(GID, channel_ids=[700], aksi="lapor")
    honeypot.set_honeypot(GID, aksi="nuklir")
    assert honeypot.status(GID)["aksi"] == "lapor"

    honeypot.set_honeypot(GID, aksi="timeout", timeout_sec=5)
    assert honeypot.status(GID)["timeout_sec"] == 60
    honeypot.set_honeypot(GID, timeout_sec=999999)
    assert honeypot.status(GID)["timeout_sec"] == 86400


def test_mematikan_tidak_menghapus_channel():
    _siapkan("hapus")
    honeypot.set_honeypot(GID, enabled=False)
    data = honeypot.status(GID)
    assert data["aktif"] is False
    assert data["channel_ids"] == [700]
    assert honeypot.is_honeypot_channel(GID, 700) is False

    honeypot.set_honeypot(GID, enabled=True)
    assert honeypot.is_honeypot_channel(GID, 700) is True


def test_tanpa_channel_otomatis_nonaktif():
    cfg = honeypot.set_honeypot(GID, channel_ids=[])
    assert cfg["enabled"] is False
    assert honeypot.status(GID)["aktif"] is False


def test_clear_honeypot():
    _siapkan()
    assert honeypot.clear_honeypot(GID) is True
    assert honeypot.clear_honeypot(GID) is False
    assert honeypot.status(GID)["channel_ids"] == []


def test_channel_dihapus_dibuang_dari_daftar():
    honeypot.set_honeypot(GID, channel_ids=[700, 701])
    kanal = _Kanal(700)
    assert honeypot.handle_channel_delete(kanal) is True
    assert honeypot.status(GID)["channel_ids"] == [701]

    honeypot.handle_channel_delete(_Kanal(701))
    data = honeypot.status(GID)
    assert data["channel_ids"] == []
    assert data["aktif"] is False


# ==============================================================================
# SIMULASI (TANPA TINDAKAN)
# ==============================================================================
def test_simulasi_member_biasa_kena_tanpa_mengubah_state():
    _siapkan("timeout")
    hasil = honeypot.akan_tertangkap(GID, 700)
    assert hasil["kena"] is True
    assert hasil["aksi"] == "timeout"
    # Simulasi tidak boleh menaikkan hitungan maupun mencatat kejadian.
    data = honeypot.status(GID)
    assert data["tangkap"] == 0
    assert data["terakhir"] == {}


def test_simulasi_mengecualikan_bot_staf_dan_channel_lain():
    _siapkan("ban")
    assert honeypot.akan_tertangkap(GID, 700, is_bot=True)["kena"] is False
    assert honeypot.akan_tertangkap(GID, 700, is_staf=True)["kena"] is False
    assert honeypot.akan_tertangkap(GID, 999)["kena"] is False
    # Staf tetap kena bila Admin mematikan "abaikan staf".
    honeypot.set_honeypot(GID, abaikan_staf=False)
    assert honeypot.akan_tertangkap(GID, 700, is_staf=True)["kena"] is True


def test_simulasi_menjelaskan_saat_honeypot_nonaktif():
    hasil = honeypot.akan_tertangkap(GID, 700)
    assert hasil["kena"] is False
    assert "belum aktif" in hasil["alasan"].lower()


# ==============================================================================
# EKSEKUSI
# ==============================================================================
@pytest.mark.asyncio
async def test_mode_lapor_tidak_menghapus_apa_pun():
    _siapkan("lapor")
    penulis, kanal = _Anggota(), _Kanal(700)
    pesan = _Pesan(penulis, kanal)
    assert await honeypot.handle_honeypot(pesan) is True
    assert pesan.deleted is False
    assert penulis.timeout_calls == []
    data = honeypot.status(GID)
    assert data["tangkap"] == 1
    assert data["terakhir"]["user_id"] == penulis.id
    assert data["terakhir"]["aksi"] == "lapor"


@pytest.mark.asyncio
async def test_mode_hapus_tidak_menghukum():
    _siapkan("hapus")
    penulis, pesan = _Anggota(), _Pesan(_Anggota(), _Kanal(700))
    pesan.author = penulis
    await honeypot.handle_honeypot(pesan)
    assert pesan.deleted is True
    assert penulis.timeout_calls == []
    assert penulis.ban_calls == []


@pytest.mark.asyncio
async def test_mode_timeout_memakai_durasi_dari_setelan():
    _siapkan("timeout", timeout_sec=420)
    penulis, pesan = _Anggota(), _Pesan(_Anggota(), _Kanal(700))
    pesan.author = penulis
    await honeypot.handle_honeypot(pesan)
    assert pesan.deleted is True
    assert len(penulis.timeout_calls) == 1
    assert penulis.timeout_calls[0][0].total_seconds() == 420


@pytest.mark.asyncio
@pytest.mark.parametrize("aksi", ["kick", "ban"])
async def test_mode_kick_dan_ban(aksi):
    _siapkan(aksi)
    penulis, pesan = _Anggota(), _Pesan(_Anggota(), _Kanal(700))
    pesan.author = penulis
    await honeypot.handle_honeypot(pesan)
    assert pesan.deleted is True
    assert len(getattr(penulis, f"{aksi}_calls")) == 1


@pytest.mark.asyncio
async def test_staf_dan_bot_tidak_ditindak():
    _siapkan("ban")
    staf = _Anggota(izin=_Izin(administrator=True))
    pesan = _Pesan(staf, _Kanal(700))
    assert await honeypot.handle_honeypot(pesan) is False
    assert pesan.deleted is False
    assert staf.ban_calls == []

    bot_lain = _Anggota(uid=777, bot=True)
    assert await honeypot.handle_honeypot(_Pesan(bot_lain, _Kanal(700))) is False
    assert honeypot.status(GID)["tangkap"] == 0


@pytest.mark.asyncio
async def test_pemilik_server_dianggap_staf():
    _siapkan("ban")
    pemilik = _Anggota(uid=42, owner_id=42)
    assert await honeypot.handle_honeypot(_Pesan(pemilik, _Kanal(700))) is False
    assert pemilik.ban_calls == []


@pytest.mark.asyncio
async def test_channel_biasa_dan_honeypot_nonaktif_diabaikan():
    _siapkan("ban")
    penulis = _Anggota()
    assert await honeypot.handle_honeypot(_Pesan(penulis, _Kanal(999))) is False
    honeypot.set_honeypot(GID, enabled=False)
    assert await honeypot.handle_honeypot(_Pesan(penulis, _Kanal(700))) is False
    assert penulis.ban_calls == []


@pytest.mark.asyncio
async def test_laporan_dikirim_ke_channel_log():
    honeypot.set_honeypot(GID, channel_ids=[700], aksi="hapus", log_channel_id=808)
    kanal_log = _Kanal(808)
    bot = type("B", (), {"get_channel": lambda _self, cid: kanal_log if cid == 808 else None})()
    await honeypot.handle_honeypot(_Pesan(_Anggota(), _Kanal(700)), bot=bot)
    assert len(kanal_log.kirim) == 1
    embed = kanal_log.kirim[0]["embed"]
    assert "Honeypot" in embed.title


def test_embed_laporan_menyebut_tindakan():
    cfg = honeypot.set_honeypot(GID, channel_ids=[700], aksi="kick")
    embed = honeypot.build_log_embed(
        _Kanal(700).guild, _Anggota(nama="Spammer"), _Kanal(700), cfg
    )
    nilai = " ".join(f.value for f in embed.fields)
    assert honeypot.AKSI_HONEYPOT["kick"] in nilai
    assert "Spammer" in nilai


# ==============================================================================
# PERMUKAAN DASHBOARD
# ==============================================================================
def test_blok_dashboard_menampilkan_setelan_dan_tombol():
    honeypot.set_honeypot(GID, channel_ids=[700], aksi="timeout", timeout_sec=300)
    html = dashboard_ui.render_honeypot_block(None, GID, "tok")
    assert 'id="p-honeypot"' in html
    assert "honeypot-simpan" in html
    assert "honeypot-hapus" in html
    assert "🪤" in html


def test_blok_dashboard_kosong_tetap_bisa_diisi():
    html = dashboard_ui.render_honeypot_block(None, GID, "tok")
    assert "Channel jebakan" in html
    assert "honeypot-simpan" in html


def test_panel_honeypot_menempel_di_halaman_keamanan():
    # Grup panel → halaman (dipakai dashboard untuk memecah tab).
    assert web_dashboard.ANCHOR_HALAMAN["p-honeypot"] == "keamanan"
    # Tombol tes honeypot ada di halaman Keamanan, bukan halaman lain.
    assert "honeypot" in web_dashboard.UJI_HALAMAN["keamanan"]
    assert all(
        "honeypot" not in kunci
        for nama, kunci in web_dashboard.UJI_HALAMAN.items()
        if nama != "keamanan"
    )


def test_registry_penguji_berisi_honeypot_di_halaman_keamanan():
    entri = {i["kunci"]: i for i in dashboard_uji.UJI}
    assert "honeypot" in entri
    assert entri["honeypot"]["grup"] == "Keamanan"
    assert dashboard_uji.ANCHOR_UJI["honeypot"] == "p-honeypot"


def test_penguji_honeypot_hanya_simulasi():
    ok, pesan = dashboard_uji._uji_honeypot(None, GID)
    assert ok is False
    assert "honeypot" in pesan.lower()

    honeypot.set_honeypot(GID, channel_ids=[700], aksi="ban")
    ok, pesan = dashboard_uji._uji_honeypot(None, GID)
    assert ok is True
    assert "Simulasi saja" in pesan
    # Tidak ada yang tercatat hanya karena simulasi dijalankan.
    assert honeypot.status(GID)["tangkap"] == 0
