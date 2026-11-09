"""Tes Paket D#1 — Reddit & RSS/Atom generik di mesin notifikasi sosial + panelnya."""

from __future__ import annotations

import pytest

import dashboard_sosial
import dashboard_uji
import social_notify as sn
import web_dashboard

GID = 123456789012345678
TOKEN = "tok"


@pytest.fixture(autouse=True)
def _bersih(monkeypatch):
    sn.social_guilds.clear()
    sn._last_checked.clear()

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(sn, "save_social_to_disk", _noop)
    yield
    sn.social_guilds.clear()


# --------------------------------------------------------------------------- #
# Platform baru
# --------------------------------------------------------------------------- #

def test_platform_baru_terdaftar():
    for kunci in ("reddit", "rss"):
        meta = sn.PLATFORMS[kunci]
        for wajib in ("label", "emoji", "hint", "template"):
            assert meta.get(wajib), (kunci, wajib)
        assert sn.PLATFORM_INTERVAL[kunci] >= 300


def test_normalize_subreddit():
    assert sn.normalize_subreddit("r/indonesia") == "indonesia"
    assert sn.normalize_subreddit("/r/aww") == "aww"
    assert sn.normalize_subreddit("indonesia") == "indonesia"
    assert sn.normalize_subreddit("https://www.reddit.com/r/gaming/new/.rss") == "gaming"
    assert sn.normalize_subreddit("https://old.reddit.com/r/python/") == "python"
    assert sn.normalize_subreddit("sub with space") == ""
    assert sn.normalize_subreddit("https://contoh.com/r/x") == ""
    assert sn.normalize_subreddit("") == ""


def test_feed_url():
    assert sn.feed_url("reddit", "r/indonesia") == "https://www.reddit.com/r/indonesia/new/.rss"
    assert sn.feed_url("rss", "https://blog.contoh.com/feed.xml") == "https://blog.contoh.com/feed.xml"
    assert sn.feed_url("tiktok", " https://rsshub.app/tiktok/user/@a ") == (
        "https://rsshub.app/tiktok/user/@a"
    )


# --------------------------------------------------------------------------- #
# Langganan
# --------------------------------------------------------------------------- #

def test_tambah_langganan_reddit_dinormalkan():
    sub = sn.add_subscription(GID, "reddit", "https://www.reddit.com/r/indonesia/", 700)
    assert sub["platform"] == "reddit" and sub["target"] == "indonesia"
    assert sub["seeded"] is False and sub["seen"] == []
    # id stabil & tidak dobel
    sama = sn.add_subscription(GID, "reddit", "r/indonesia", 701)
    assert sama["id"] == sub["id"] and sama["channel_id"] == 701
    assert len(sn.get_subscriptions(GID)) == 1


def test_tambah_langganan_rss_wajib_url():
    sub = sn.add_subscription(GID, "rss", "https://blog.contoh.com/feed.xml", 700)
    assert sub["platform"] == "rss" and sub["template"] == ""
    with pytest.raises(ValueError) as galat:
        sn.add_subscription(GID, "rss", "blog.contoh.com/feed.xml", 700)
    assert "URL feed" in str(galat.value)
    with pytest.raises(ValueError) as galat2:
        sn.add_subscription(GID, "reddit", "sub yang salah!", 700)
    assert "subreddit" in str(galat2.value)


def test_batas_langganan_per_server():
    for i in range(sn.MAX_SUBS_PER_GUILD):
        sn.add_subscription(GID, "rss", f"https://contoh.com/feed{i}.xml", 700)
    with pytest.raises(ValueError) as galat:
        sn.add_subscription(GID, "rss", "https://contoh.com/feed-extra.xml", 700)
    assert "Batas" in str(galat.value)


# --------------------------------------------------------------------------- #
# Parser Reddit
# --------------------------------------------------------------------------- #

ATOM_REDDIT = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>r/indonesia</title>
  <entry>
    <title>Postingan pertama</title>
    <link href="https://www.reddit.com/r/indonesia/comments/abc/pertama/" />
    <id>t3_abc</id>
    <updated>2026-01-02T03:04:05+00:00</updated>
  </entry>
  <entry>
    <title>Postingan kedua</title>
    <link href="https://www.reddit.com/r/indonesia/comments/def/kedua/" />
    <id>t3_def</id>
    <published>2026-01-03T03:04:05+00:00</published>
  </entry>
</feed>
"""


def test_parse_reddit_feed():
    items = sn.parse_reddit_feed(ATOM_REDDIT)
    assert len(items) == 2
    assert items[0]["title"] == "Postingan pertama"
    assert items[0]["url"].startswith("https://www.reddit.com/r/indonesia/comments/abc/")
    assert items[0]["source"] == "r/indonesia"
    assert items[0]["id"] != items[1]["id"]
    assert items[1]["published"].startswith("2026-01-03")
    assert sn.parse_reddit_feed(b"<bukan-xml") == []


@pytest.mark.asyncio
async def test_ambil_feed_reddit_pakai_url_kanonis(monkeypatch):
    dipanggil = {}

    async def palsu(session, url, *, headers=None):
        dipanggil["url"] = url
        return ATOM_REDDIT

    monkeypatch.setattr(sn, "fetch_text", palsu)
    sub = sn.add_subscription(GID, "reddit", "r/indonesia", 700)
    items = await sn.fetch_feed_items(None, sub)
    assert dipanggil["url"] == "https://www.reddit.com/r/indonesia/new/.rss"
    assert [item["title"] for item in items] == ["Postingan pertama", "Postingan kedua"]


# --------------------------------------------------------------------------- #
# Panel dashboard
# --------------------------------------------------------------------------- #

def _guild():
    from types import SimpleNamespace

    kanal = [
        SimpleNamespace(id=700, name="notifikasi"),
        SimpleNamespace(id=701, name="umum"),
    ]
    role = SimpleNamespace(id=900, name="Penggemar", is_default=lambda: False)
    return SimpleNamespace(
        id=GID,
        text_channels=kanal,
        roles=[SimpleNamespace(id=GID, name="@everyone", is_default=lambda: True), role],
        get_channel=lambda cid: next((ch for ch in kanal if ch.id == cid), None),
    )


def _bot(guild=None):
    from types import SimpleNamespace

    return SimpleNamespace(get_guild=lambda gid: guild)


def test_panel_sosial_menampilkan_form_dan_langganan():
    sn.add_subscription(GID, "reddit", "r/indonesia", 700)
    sn.add_subscription(GID, "rss", "https://blog.contoh.com/feed.xml", 700)
    html = dashboard_sosial.render_sosial_block(_bot(_guild()), GID, TOKEN)
    assert 'class="subpanel" id="p-sosial"' in html
    assert 'id="sosial-platform"' in html
    assert 'value="reddit"' in html and 'value="rss"' in html
    assert "sosial-tambah" in html
    assert "https://www.reddit.com/r/indonesia/new/.rss" in html
    assert "https://blog.contoh.com/feed.xml" in html
    assert html.count("sosial-hapus:") == 2
    assert "#notifikasi" in html  # nama channel muncul
    assert "Penggemar" in html  # role bisa dipilih, @everyone tidak
    assert "@everyone" not in html


def test_panel_sosial_kosong_dan_tanpa_guild():
    html = dashboard_sosial.render_sosial_block(None, GID, TOKEN)
    assert "Belum ada langganan" in html
    assert "belum ada channel teks" in html


@pytest.mark.asyncio
async def test_aksi_sosial_tambah_dan_hapus():
    ok, pesan = await dashboard_sosial.aksi_sosial(
        GID, "sosial-tambah",
        {"platform": "reddit", "target": "r/indonesia", "channel_id": "700", "role_id": "900"},
    )
    assert ok and "reddit.com/r/indonesia/new/.rss" in pesan
    sub = sn.get_subscriptions(GID)[0]
    assert sub["role_id"] == 900

    ok, pesan = await dashboard_sosial.aksi_sosial(
        GID, f"sosial-hapus:{sub['id']}", {}
    )
    assert ok and sn.get_subscriptions(GID) == []

    ok, pesan = await dashboard_sosial.aksi_sosial(GID, "sosial-hapus:tidakada", {})
    assert ok is False and "sudah tidak ada" in pesan


@pytest.mark.asyncio
async def test_aksi_sosial_menolak_input_tidak_valid():
    ok, pesan = await dashboard_sosial.aksi_sosial(GID, "sosial-tambah", {"platform": "x"})
    assert ok is False and "platform" in pesan
    ok, pesan = await dashboard_sosial.aksi_sosial(
        GID, "sosial-tambah", {"platform": "rss", "target": "https://a.com/f.xml"}
    )
    assert ok is False and "channel" in pesan
    ok, pesan = await dashboard_sosial.aksi_sosial(
        GID, "sosial-tambah",
        {"platform": "rss", "target": "a.com/f.xml", "channel_id": "700"},
    )
    assert ok is False and "URL feed" in pesan
    ok, pesan = await dashboard_sosial.aksi_sosial(GID, "sosial-ngawur", {})
    assert ok is False and "tidak dikenal" in pesan


# --------------------------------------------------------------------------- #
# Wiring halaman & penguji
# --------------------------------------------------------------------------- #

def test_sosial_menempel_di_halaman_interaksi():
    assert web_dashboard.ANCHOR_HALAMAN["p-sosial"] == "interaksi"
    peta = {kunci: slug for slug, daftar in web_dashboard.UJI_HALAMAN.items() for kunci in daftar}
    assert peta["sosial"] == "interaksi"
    assert dashboard_uji.ANCHOR_UJI["sosial"] == "p-sosial"
    assert dashboard_uji.UJI_MAP["sosial"]["grup"] == "Konten & interaksi"


def test_uji_sosial_simulasi_tanpa_jaringan():
    ok, pesan = dashboard_uji._uji_sosial(GID)
    assert ok is False and "Belum ada langganan" in pesan

    sn.add_subscription(GID, "reddit", "r/indonesia", 700)
    ok, pesan = dashboard_uji._uji_sosial(GID)
    assert ok is True and "simulasi" in pesan
    assert "reddit.com/r/indonesia" in pesan
