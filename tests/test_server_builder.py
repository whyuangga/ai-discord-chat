"""Tes Paket E#1 — pembangun server instan (tema Instabot + perancang AI)."""

from __future__ import annotations

import json

import pytest

import server_builder as sb

GID = 555000111222333444


@pytest.fixture(autouse=True)
def _bersih(monkeypatch, tmp_path):
    sb.reset_state()
    monkeypatch.setattr(sb, "BUILDER_FILE", tmp_path / "server_builder.json")
    yield
    sb.reset_state()


class _Role:
    def __init__(self, nama):
        self.name = nama

    def is_default(self):
        return self.name == "@everyone"

    async def delete(self, reason=""):
        self.deleted = True


class _Channel:
    def __init__(self, nama, jenis="text"):
        self.name = nama
        self.type = jenis
        self.deleted = False

    async def delete(self, reason=""):
        self.deleted = True


class _Kategori(_Channel):
    def __init__(self, nama):
        super().__init__(nama, "category")


class _Guild:
    """Server palsu minimal untuk `backup_restore.apply_plan` & bongkar."""

    def __init__(self, nama="Server Uji"):
        self.id = GID
        self.name = nama
        self.roles = [_Role("@everyone")]
        self.categories: list[_Kategori] = []
        self.channels: list[_Channel] = []
        self.created = {"roles": [], "categories": [], "channels": []}

    async def create_role(self, name, **kwargs):
        self.roles.append(_Role(name))
        self.created["roles"].append(name)
        return self.roles[-1]

    async def create_category(self, name, **kwargs):
        item = _Kategori(name)
        self.categories.append(item)
        self.created["categories"].append(name)
        return item

    async def create_text_channel(self, name, **kwargs):
        item = _Channel(name)
        self.channels.append(item)
        self.created["channels"].append(name)
        return item

    async def create_voice_channel(self, name, **kwargs):
        item = _Channel(name, "voice")
        self.channels.append(item)
        self.created["channels"].append(name)
        return item


# --------------------------------------------------------------------------- #
# Tema bawaan
# --------------------------------------------------------------------------- #

def test_lima_belas_tema_dan_autocomplete():
    tema = sb.daftar_tema()
    assert len(tema) == 15
    assert all(item["label"] and item["emoji"] for item in tema)
    ids = {item["id"] for item in tema}
    assert {"gaming", "komunitas", "aesthetic", "study", "coding"} <= ids


def test_cari_tema_toleran():
    assert sb.cari_tema("GAMING") == "gaming"
    assert sb.cari_tema("gaming") == "gaming"
    assert sb.cari_tema("Gaming / Esport") == "gaming"
    assert sb.cari_tema("🎮") == "gaming"
    assert sb.cari_tema("aesthetic") == "aesthetic"
    assert sb.cari_tema("") is None
    assert sb.cari_tema("zzz") is None


def test_tebak_tema_dari_deskripsi():
    assert sb.tema_dari_deskripsi("server buat mabar valorant dan esport") == "gaming"
    assert sb.tema_dari_deskripsi("komunitas belajar python") == "komunitas"  # kata eksplisit menang
    assert sb.tema_dari_deskripsi("tanya jawab programming javascript") == "coding"
    assert sb.tema_dari_deskripsi("belajar buat ujian sekolah") == "study"
    assert sb.tema_dari_deskripsi("kumpulan otaku anime") == "anime"
    assert sb.tema_dari_deskripsi("apalah") == "komunitas"  # jatuh ke bawaan


def test_snapshot_tema_valid_dan_berisi_role():
    snap = sb.tema_ke_snapshot("gaming", nama_server="Esport ID")
    assert snap["meta"]["sumber"] == "tema:gaming"
    assert snap["meta"]["guild_name"] == "Esport ID"
    assert len(snap["categories"]) == 3
    assert any(item["type"] == "voice" for item in snap["channels"])
    assert snap["roles"] and snap["roles"][0]["hoist"] is True
    ok, alasan = sb.validasi(snap)
    assert ok, alasan
    teks = sb.ringkas(snap)
    assert "INFORMASI" in teks and "Player" in teks and "channel" in teks


def test_semua_tema_lolos_validasi():
    for item in sb.daftar_tema():
        snap = sb.tema_ke_snapshot(item["id"])
        ok, alasan = sb.validasi(snap)
        assert ok, (item["id"], alasan)


# --------------------------------------------------------------------------- #
# Validasi & normalisasi
# --------------------------------------------------------------------------- #

def test_validasi_menolak_struktur_berlebih():
    ok, alasan = sb.validasi({"channels": []})
    assert not ok and "channel" in alasan

    banyak = {"channels": [{"name": f"c{i}", "type": "text"} for i in range(sb.MAKS_CHANNEL + 1)]}
    assert sb.validasi(banyak)[0] is False

    asing = {"channels": [{"name": "x", "type": "radio"}]}
    assert sb.validasi(asing)[0] is False

    kategori = {"channels": [{"name": "x", "type": "text"}],
                "categories": [{"name": f"k{i}"} for i in range(sb.MAKS_KATEGORI + 1)]}
    assert sb.validasi(kategori)[0] is False
    assert sb.validasi("bukan dict")[0] is False


def test_normalisasi_membuang_duplikat_dan_field_asing():
    snap = sb.normalisasi(
        {
            "roles": [{"name": "  Admin  ", "colour": 10, "izin_ajaib": 1}, {"name": ""}],
            "categories": [{"name": "INFO"}, {"name": "info"}, {"name": "  "}],
            "channels": [
                {"name": "umum", "type": "TEXT", "category": "info", "topic": "Halo"},
                {"name": "asing", "type": "radio"},
                {"name": "", "type": "text"},
                {"name": "suara", "type": "voice", "category": "tidak-ada"},
            ],
        },
        label="Rancangan",
    )
    assert [r["name"] for r in snap["roles"]] == ["Admin"]
    assert [c["name"] for c in snap["categories"]] == ["INFO"]
    nama = [c["name"] for c in snap["channels"]]
    assert nama == ["umum", "asing", "suara"]
    assert snap["channels"][0]["topic"] == "Halo"
    assert snap["channels"][1]["type"] == "text"  # tipe asing → text
    assert "category" not in snap["channels"][2]  # kategori tak dikenal dibuang
    assert snap["meta"]["label"] == "Rancangan"


# --------------------------------------------------------------------------- #
# Perancang AI
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_rancang_tanpa_ai_memakai_tema():
    snap, sumber = await sb.rancang("server untuk main minecraft bareng")
    assert sumber.startswith("tema:")
    assert snap["channels"]


@pytest.mark.asyncio
async def test_rancang_memakai_ai_json_berpagar():
    async def ai_call(prompt):
        assert "JSON" in prompt
        return '```json\n{"roles":[{"name":"Founder"}],"categories":[{"name":"TIM"}],\n"channels":[{"name":"umum","type":"text","category":"TIM"}]}\n```'

    snap, sumber = await sb.rancang("startup SaaS kecil", ai_call=ai_call)
    assert sumber == "ai"
    assert snap["roles"][0]["name"] == "Founder"
    assert sb.validasi(snap)[0] is True


@pytest.mark.asyncio
async def test_rancang_ai_rusak_jatuh_ke_tema():
    async def ai_call(prompt):
        return "maaf, saya tidak bisa"

    snap, sumber = await sb.rancang("server gaming mobile legends", ai_call=ai_call)
    assert sumber.startswith("tema:")
    assert snap["meta"]["sumber"] == "tema:gaming"


# --------------------------------------------------------------------------- #
# Terapkan & bongkar
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_terapkan_dan_bongkar(monkeypatch):
    import backup_restore as br

    monkeypatch.setattr(br, "CREATE_DELAY_SEC", 0)

    guild = _Guild()
    snap = sb.tema_ke_snapshot("study")
    hasil, pesan = await sb.terapkan(guild, snap, actor_id=7)

    assert hasil["roles"] == len(snap["roles"])
    assert hasil["categories"] == len(snap["categories"])
    assert hasil["channels"] == len(snap["channels"])
    assert "Dibuat" in pesan

    data = sb.riwayat[GID]
    assert data["oleh"] == 7 and data["label"]
    assert len(data["dibuat"]["channels"]) == len(snap["channels"])

    ok, pesan = await sb.bongkar(guild)
    assert ok and "dihapus" in pesan
    assert all(item.deleted for item in guild.channels)
    assert GID not in sb.riwayat

    ok2, pesan2 = await sb.bongkar(guild)
    assert not ok2 and "Belum ada" in pesan2


def test_ringkas_hasil_dengan_galat():
    pesan = sb.ringkas_hasil(
        {"roles": 1, "categories": 1, "channels": 2,
         "errors": ["role `X`: Forbidden", "channel `y`: HTTPException", "z"]}
    )
    assert "Dibuat" in pesan and "dilewati" in pesan and "role `X`" in pesan


# --------------------------------------------------------------------------- #
# Simpan & muat
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_simpan_dan_muat_riwayat():
    sb.riwayat[GID] = {
        "pada": 100.0,
        "label": "Gaming",
        "oleh": 3,
        "dibuat": {"roles": ["Player"], "categories": ["INFO"], "channels": ["umum"]},
        "hasil": {"roles": 1, "categories": 1, "channels": 1, "errors": []},
    }
    await sb.save_to_disk()
    sb.reset_state()
    assert sb.load_from_disk() == 1
    assert sb.riwayat[GID]["dibuat"]["channels"] == ["umum"]
    assert sb.riwayat[GID]["oleh"] == 3


def test_muat_berkas_rusak_diabaikan():
    from pathlib import Path

    Path(sb.BUILDER_FILE).write_text("{rusak", encoding="utf-8")
    assert sb.load_from_disk() == 0
    Path(sb.BUILDER_FILE).write_text(json.dumps({"guilds": {"abc": {}, str(GID): {"label": "x"}}}),
                                     encoding="utf-8")
    assert sb.load_from_disk() == 1
