"""Fitur ber-channel bisa memakai **beberapa** channel sekaligus.

Koran pagi (digest) & fakta harian tetap satu channel sesuai permintaan.
"""

from __future__ import annotations

import types

import channel_targets
import dashboard_admin
import web_dashboard

GID = 4321


# ==============================================================================
# HELPER
# ==============================================================================
def test_parse_berbagai_bentuk():
    assert channel_targets.parse("101, 102,103") == [101, 102, 103]
    assert channel_targets.parse(["101", "102"]) == [101, 102]
    assert channel_targets.parse("<#101>") == [101]
    assert channel_targets.parse(0) == [] and channel_targets.parse("") == []
    assert channel_targets.parse("101,101") == [101]          # duplikat dibuang


def test_daftar_kompatibel_dengan_config_lama():
    # Config lama hanya punya satu channel
    assert channel_targets.daftar({"channel_id": 5}) == [5]
    # Config baru punya daftar; kunci tunggal = channel pertama
    assert channel_targets.daftar({"channel_id": 5, "channel_ids": [5, 6]}) == [5, 6]
    assert channel_targets.daftar({"log_channel_id": 7}, "log_channel_id") == [7]
    assert channel_targets.daftar({}) == []


def test_setel_dan_cocok():
    cfg: dict = {}
    channel_targets.setel(cfg, "11,12", "log_channel_id")
    assert cfg["log_channel_ids"] == [11, 12]
    assert cfg["log_channel_id"] == 11
    assert channel_targets.cocok(cfg, 12, "log_channel_id") is True
    assert channel_targets.cocok(cfg, 13, "log_channel_id") is False
    channel_targets.setel(cfg, "", "log_channel_id")
    assert cfg["log_channel_ids"] == [] and cfg["log_channel_id"] is None


def test_label_ringkas():
    assert channel_targets.label([1, 2]) == "<#1>, <#2>"
    assert "+1 lagi" in channel_targets.label([1, 2, 3, 4, 5])


# ==============================================================================
# SETELAN: HANYA DIGEST & FAKTA YANG TETAP SATU CHANNEL
# ==============================================================================
def test_digest_dan_fakta_tetap_satu_channel():
    assert dashboard_admin.FITUR["digest.channel"]["jenis"] == "channel"
    assert dashboard_admin.FITUR["fakta.channel"]["jenis"] == "channel"
    # Fitur siaran lain sudah multi-channel
    for kunci in ("sambutan.channel", "pamit.channel", "boost.channel", "level.channel",
                  "antispam.log", "antinuke.log", "tiket.log", "ultah.channel",
                  "backup.channel", "chat.channel", "galeri.channel", "youtube.channel",
                  "cari.channel", "terjemah.channel"):
        assert dashboard_admin.FITUR[kunci]["jenis"] == "channels", kunci


async def test_setelan_multi_menyimpan_dan_membaca_dua_channel():
    import community_agent as ca

    ca.welcome_agent_guilds.pop(GID, None)
    ok, pesan = await dashboard_admin.apply(GID, "sambutan.channel", "101,102")
    assert ok and "2 channel" in pesan
    cfg = ca.welcome_agent_guilds[GID]
    assert cfg["channel_ids"] == [101, 102]
    assert cfg["channel_id"] == 101                     # tetap sinkron untuk kode lama
    assert dashboard_admin.read_values(GID)["sambutan.channel"] == "101,102"

    # Centang “Kosongkan” mematikan fitur
    ok, _ = await dashboard_admin.apply(GID, "sambutan.channel", "0")
    assert ok and GID not in ca.welcome_agent_guilds


async def test_agen_ai_multi_channel():
    import community_agent as ca

    ca.chat_agent_channels.clear()
    ok, pesan = await dashboard_admin.apply(GID, "chat.channel", "201,202")
    assert ok and "2 channel" in pesan
    assert set(ca.chat_agent_channels) == {201, 202}
    # Mengurangi pilihan mematikan channel yang dilepas
    await dashboard_admin.apply(GID, "chat.channel", "202")
    assert set(ca.chat_agent_channels) == {202}


def test_kontrol_checkbox_menampilkan_semua_channel():
    import dashboard_ui

    class _Ch:
        def __init__(self, cid, nama):
            self.id, self.name = cid, nama

    class _G:
        id = GID
        text_channels = [_Ch(101, "umum"), _Ch(102, "sambutan")]
        channels = text_channels

        def get_channels(self):
            return list(self.text_channels)

    class _B:
        def get_guild(self, gid):
            return _G()

    html = dashboard_ui.kontrol_html("sambutan.channel", "101", _B(), GID)
    assert 'class="channel-grid"' in html
    assert html.count('type="checkbox"') == 3        # 2 channel + “Kosongkan”
    assert 'value="101" checked' in html
    assert 'value="102" checked' not in html


# ==============================================================================
# PENGIRIMAN: FAN-OUT KE SEMUA CHANNEL
# ==============================================================================
class _Kanal:
    def __init__(self, cid):
        self.id = cid
        self.terkirim: list = []

    async def send(self, **kwargs):
        self.terkirim.append(kwargs)


class _BotKanal:
    def __init__(self):
        self.kanal = {11: _Kanal(11), 12: _Kanal(12)}

    def get_channel(self, cid):
        return self.kanal.get(int(cid))


async def test_log_antispam_terkirim_ke_semua_channel():
    import antispam
    import discord

    bot = _BotKanal()
    cfg = {"log_channel_ids": [11, 12]}
    embed = discord.Embed(title="Spam")
    ok = await antispam._notify(bot, cfg, None, embed)
    assert ok is True
    assert bot.kanal[11].terkirim and bot.kanal[12].terkirim


async def test_log_antinuke_terkirim_ke_semua_channel():
    import antinuke
    import discord

    bot = _BotKanal()
    await antinuke._notify(bot, types.SimpleNamespace(system_channel=None),
                           {"log_channel_ids": [11, 12]}, discord.Embed(title="Nuke"))
    assert bot.kanal[11].terkirim and bot.kanal[12].terkirim


async def test_sebarkan_lewati_channel_hilang():
    bot = _BotKanal()
    dipakai = []

    async def kirim(ch):
        dipakai.append(ch.id)

    jumlah = await channel_targets.sebarkan(bot, [11, 999, 12], kirim)
    assert jumlah == 2 and dipakai == [11, 12]


def test_form_multi_nilai_digabung_jadi_csv():
    """Form HTML mengirim beberapa `value` (checkbox) → dashboard membacanya sebagai CSV."""
    assert web_dashboard.url_halaman("sambutan", "t", GID).startswith("/sambutan?token=t")
