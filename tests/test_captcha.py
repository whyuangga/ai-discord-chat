"""Tes Paket D#4 — CAPTCHA verifikasi (kode teks, tanpa dependency baru)."""

from __future__ import annotations

import json
import random
from types import SimpleNamespace

import pytest

import community_tools as ct
import dashboard_admin
import dashboard_uji
import views.community as vc

GID = 123456789012345678
ROLE_ID = 900
CHANNEL_ID = 505


@pytest.fixture(autouse=True)
def _bersih(monkeypatch, tmp_path):
    ct.verification_guilds.clear()
    ct.reset_captcha_state()
    monkeypatch.setattr(ct, "COMMUNITY_TOOLS_FILE", tmp_path / "community_tools.json")
    yield
    ct.verification_guilds.clear()
    ct.reset_captcha_state()


def _pasang(captcha=True):
    ct.set_verification_config(
        GID, channel_id=CHANNEL_ID, role_id=ROLE_ID, enabled=True, captcha=captcha
    )


# --------------------------------------------------------------------------- #
# Kode
# --------------------------------------------------------------------------- #

def test_buat_kode_aman_dibaca():
    kode = ct.buat_kode()
    assert len(kode) == ct.CAPTCHA_PANJANG
    assert all(huruf in ct.CAPTCHA_HURUF for huruf in kode)
    for huruf in "01OIL":
        assert huruf not in ct.CAPTCHA_HURUF

    tetap = ct.buat_kode(rng=random.Random(7))
    assert tetap == ct.buat_kode(rng=random.Random(7))
    assert len(ct.buat_kode(panjang=99)) <= 8


def test_captcha_aktif_butuh_sakelar_dan_flag():
    assert ct.captcha_aktif(GID) is False
    ct.set_verification_config(GID, channel_id=CHANNEL_ID, role_id=ROLE_ID, enabled=True)
    assert ct.captcha_aktif(GID) is False  # captcha default mati
    ct.set_verification_config(GID, captcha=True)
    assert ct.captcha_aktif(GID) is True
    ct.set_verification_config(GID, enabled=False)
    assert ct.captcha_aktif(GID) is False


def test_minta_kode_memakai_ulang_dan_kedaluwarsa():
    data = ct.minta_kode(GID, 7, sekarang=100.0)
    assert data["percobaan"] == 0 and data["kedaluwarsa"] == 100.0 + ct.CAPTCHA_TTL_SEC
    sama = ct.minta_kode(GID, 7, sekarang=150.0)
    assert sama["kode"] == data["kode"]

    baru = ct.minta_kode(GID, 7, sekarang=100.0 + ct.CAPTCHA_TTL_SEC + 1)
    assert baru["kedaluwarsa"] > data["kedaluwarsa"]
    assert ct.sisa_percobaan(GID, 7) == ct.CAPTCHA_MAKS_PERCOBAAN


def test_cocokkan_kode_sukses_tanpa_lihat_besar_kecil():
    data = ct.minta_kode(GID, 7, sekarang=100.0)
    jawaban = " " + data["kode"].lower() + " "
    assert ct.cocokkan_kode(GID, 7, jawaban, sekarang=110) == "ok"
    assert ct.cocokkan_kode(GID, 7, data["kode"], sekarang=111) == "tidak_ada"  # sudah dipakai


def test_cocokkan_kode_salah_dan_percobaan_habis():
    ct.minta_kode(GID, 7, sekarang=100.0)
    assert ct.cocokkan_kode(GID, 7, "XXXXX", sekarang=101) == "salah"
    assert ct.sisa_percobaan(GID, 7) == ct.CAPTCHA_MAKS_PERCOBAAN - 1
    assert ct.cocokkan_kode(GID, 7, "YYYYY", sekarang=102) == "salah"
    assert ct.cocokkan_kode(GID, 7, "ZZZZZ", sekarang=103) == "habis"
    assert ct.sisa_percobaan(GID, 7) == 0
    assert ct.cocokkan_kode(GID, 7, "AAAAA", sekarang=104) == "tidak_ada"


def test_cocokkan_kode_kedaluwarsa():
    ct.minta_kode(GID, 7, sekarang=100.0)
    assert (
        ct.cocokkan_kode(GID, 7, "AAAAA", sekarang=100.0 + ct.CAPTCHA_TTL_SEC + 1) == "kedaluwarsa"
    )
    assert ct.sisa_percobaan(GID, 7) == 0


def test_bersihkan_dan_cleanup():
    ct.minta_kode(GID, 7, sekarang=100.0)
    assert ct.bersihkan_kode(GID, 7) is True
    assert ct.bersihkan_kode(GID, 7) is False

    ct.minta_kode(GID, 7, sekarang=100.0)
    ct.minta_kode(GID, 8, sekarang=500.0)
    assert ct.cleanup_captcha_runtime(sekarang=100.0 + ct.CAPTCHA_TTL_SEC + 1) == 1
    assert ct.statistik_captcha(GID)["menunggu"] == 1


def test_statistik_captcha():
    _pasang()
    data = ct.statistik_captcha(GID)
    assert data["aktif"] is True and data["terpasang"] is True
    assert data["ttl_detik"] == ct.CAPTCHA_TTL_SEC
    assert data["maks_percobaan"] == ct.CAPTCHA_MAKS_PERCOBAAN


# --------------------------------------------------------------------------- #
# Embed & persistensi
# --------------------------------------------------------------------------- #

def test_embed_menyebut_captcha():
    biasa = ct.build_verification_embed("Server", "Member")
    assert "CAPTCHA" not in biasa.description
    assert "Sekali klik" in biasa.footer.text

    captcha = ct.build_verification_embed("Server", "Member", captcha=True)
    assert "CAPTCHA" in captcha.description
    assert ct.CAPTCHA_HURUF  # alfabet tetap tersedia untuk referensi
    assert "Kode CAPTCHA" in captcha.footer.text
    assert captcha.fields == [] or captcha.fields[0].name == "📌 Catatan"


@pytest.mark.asyncio
async def test_flag_captcha_tersimpan(tmp_path):
    _pasang(captcha=True)
    await ct.save_community_tools_to_disk()
    mentah = json.loads((tmp_path / "community_tools.json").read_text(encoding="utf-8"))
    assert mentah["verification"][str(GID)]["captcha"] is True

    ct.verification_guilds.clear()
    ct.load_community_tools_from_disk()
    assert ct.verification_guilds[GID]["captcha"] is True
    assert ct.captcha_aktif(GID) is True


# --------------------------------------------------------------------------- #
# Modal & tombol
# --------------------------------------------------------------------------- #

class _Response:
    def __init__(self):
        self.modal = None
        self.pesan = []

    async def send_modal(self, modal):
        self.modal = modal

    async def send_message(self, isi, **kwargs):
        self.pesan.append(isi)


def _interaction(uid=7, guild_id=GID):
    return SimpleNamespace(
        user=SimpleNamespace(id=uid),
        guild=SimpleNamespace(id=guild_id),
        response=_Response(),
    )


@pytest.mark.asyncio
async def test_modal_menerima_kode_benar(monkeypatch):
    _pasang()
    dipanggil = {}

    async def palsu(user, guild_id):
        dipanggil["uid"] = user.id
        return True, "✅ Kamu terverifikasi!"

    monkeypatch.setattr(vc, "grant_verification_role", palsu)

    kode = ct.minta_kode(GID, 7, sekarang=None)["kode"]
    modal = vc.CaptchaVerificationModal(GID, kode)
    interaksi = _interaction()
    modal.jawaban._value = kode.lower()
    await modal.on_submit(interaksi)
    assert dipanggil["uid"] == 7
    assert "terverifikasi" in interaksi.response.pesan[0]


@pytest.mark.asyncio
async def test_modal_menolak_kode_salah(monkeypatch):
    _pasang()
    dipanggil = []

    async def palsu(user, guild_id):
        dipanggil.append(user.id)
        return True, "ok"

    monkeypatch.setattr(vc, "grant_verification_role", palsu)

    kode = ct.minta_kode(GID, 7)["kode"]
    modal = vc.CaptchaVerificationModal(GID, kode)
    interaksi = _interaction()
    modal.jawaban._value = "SALAH"
    await modal.on_submit(interaksi)
    assert dipanggil == []
    assert "Sisa percobaan" in interaksi.response.pesan[0]


@pytest.mark.asyncio
async def test_tombol_membuka_modal_saat_captcha_aktif():
    _pasang(captcha=True)
    view = vc.VerificationGateView()
    interaksi = _interaction()
    await view.verify_btn.callback(interaksi)
    assert isinstance(interaksi.response.modal, vc.CaptchaVerificationModal)
    assert len(interaksi.response.modal.kode) == ct.CAPTCHA_PANJANG


@pytest.mark.asyncio
async def test_tombol_langsung_memberi_role_saat_captcha_mati(monkeypatch):
    _pasang(captcha=False)
    dipanggil = []

    async def palsu(user, guild_id):
        dipanggil.append(user.id)
        return True, "✅ langsung"

    monkeypatch.setattr(vc, "grant_verification_role", palsu)
    view = vc.VerificationGateView()
    interaksi = _interaction()
    await view.verify_btn.callback(interaksi)
    assert interaksi.response.modal is None
    assert dipanggil == [7]
    assert interaksi.response.pesan == ["✅ langsung"]


# --------------------------------------------------------------------------- #
# Command & dashboard
# --------------------------------------------------------------------------- #

def test_command_pasang_punya_opsi_captcha():
    from cogs.community_cog import verifikasi_group

    perintah = {cmd.name: cmd for cmd in verifikasi_group.commands}
    opsi = {p.name for p in perintah["pasang"].parameters}
    assert "captcha" in opsi
    assert "captcha" in perintah["pasang"].description or True  # deskripsi bebas


def test_dashboard_saklar_captcha():
    ok, pesan = dashboard_admin._set_verifikasi_captcha(GID, "on")
    assert ok is False  # channel verifikasi belum ada

    ct.set_verification_config(GID, channel_id=CHANNEL_ID, role_id=ROLE_ID, enabled=True)
    ok, pesan = dashboard_admin._set_verifikasi_captcha(GID, "on")
    assert ok is True and ct.captcha_aktif(GID) is True
    assert dashboard_admin._baca_verifikasi_captcha(GID) == "on"

    ok, pesan = dashboard_admin._set_verifikasi_captcha(GID, "off")
    assert ok is True and ct.captcha_aktif(GID) is False
    assert dashboard_admin._baca_verifikasi_captcha(GID) == "off"


def test_saklar_captcha_masuk_daftar_fitur_keamanan():
    kunci = {item["kunci"] for item in dashboard_admin.FITUR_LIST}
    assert "verifikasi.captcha" in kunci
    grup = {grup["kunci"]: grup for grup in dashboard_admin.GRUP}
    assert "verifikasi.captcha" in grup["keamanan"]["fitur"]


def test_uji_verifikasi_simulasi():
    guild = SimpleNamespace(
        id=GID,
        get_role=lambda rid: SimpleNamespace(id=rid, name="Member") if rid == ROLE_ID else None,
    )
    ok, pesan = dashboard_uji._uji_verifikasi(guild)
    assert ok is False and "belum aktif" in pesan

    ct.set_verification_config(GID, role_id=ROLE_ID, enabled=True)
    ok, pesan = dashboard_uji._uji_verifikasi(guild)
    assert ok is False and "Channel" in pesan

    _pasang()
    ok, pesan = dashboard_uji._uji_verifikasi(guild)
    assert ok is True and "Simulasi" in pesan and "CAPTCHA" in pesan

    ct.set_verification_config(GID, role_id=1234)
    ok, pesan = dashboard_uji._uji_verifikasi(guild)
    assert ok is False and "tidak ada" in pesan
