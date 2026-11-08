"""Tes unit untuk helper pemuat data hasil pemecahan refactor.

**Mengapa berkas ini ada.** Refactor memecah `load_economy_from_disk` dan
`load_server_features_from_disk` menjadi helper `_muat_*`. Kesetaraannya saat
itu dijaga lewat perbandingan manual, bukan suite — jadi kalau helper ini
diubah nanti, tidak ada jaring yang menangkap kesalahan halus.

Yang diuji: penanganan **data rusak**. Berkas JSON pengguna tidak bisa
dipercaya — kunci gid bisa bukan angka, nilai bisa bertipe salah, entri bisa
separuh jadi. Semua kasus itu harus dilewati tanpa melempar exception.
"""

from __future__ import annotations

import economy
import server_features as sf


def _bersihkan_ekonomi():
    economy.economy_guilds.clear()
    economy.balances.clear()
    economy.meta.clear()
    economy.shop.clear()


def _bersihkan_server_features():
    sf.serverstats_guilds.clear()
    sf.autorole_guilds.clear()
    sf.facts_guilds.clear()
    sf.security_guilds.clear()


# ==============================================================================
# economy.py
# ==============================================================================
def test_muat_guild_ekonomi_nilai_bawaan_dan_batas():
    """Field yang hilang memakai bawaan; angka negatif dijepit ke batas bawah."""
    _bersihkan_ekonomi()
    economy._muat_guild_ekonomi(
        {
            "guilds": {
                "111": {  # semua bawaan
                    "enabled": True,
                },
                "222": {  # nilai ekstrem
                    "per_message": -50,
                    "cooldown": -1,
                    "daily_cooldown": 10,  # di bawah minimum 3600
                    "currency": "K" * 50,  # dipotong 20
                    "emoji": "E" * 40,  # dipotong 16
                },
            }
        }
    )

    assert set(economy.economy_guilds) == {111, 222}
    assert economy.economy_guilds[111]["enabled"] is True

    ekstrem = economy.economy_guilds[222]
    assert ekstrem["per_message"] == 0
    assert ekstrem["cooldown"] == 0
    assert ekstrem["daily_cooldown"] == 3600
    assert len(ekstrem["currency"]) == 20
    assert len(ekstrem["emoji"]) == 16


def test_muat_guild_ekonomi_membuang_kunci_dan_entri_rusak():
    """Kunci gid non-angka dan data bukan-dict dilewati, bukan meledak."""
    _bersihkan_ekonomi()
    economy._muat_guild_ekonomi(
        {
            "guilds": {
                "bukan-angka": {"enabled": True},
                "333": None,  # None -> dianggap kosong, tetap dimuat dengan bawaan
                "444": {"ignore_channels": [1, 0, "2", "x", None]},
            }
        }
    )

    assert "bukan-angka" not in {str(k) for k in economy.economy_guilds}
    assert 444 in economy.economy_guilds
    # 0, "x", dan None bukan channel valid -> dibuang
    assert economy.economy_guilds[444]["ignore_channels"] == [1, 2]


def test_muat_saldo_ekonomi_hanya_positif_dan_kunci_valid():
    """Saldo nol/negatif/bukan-angka dibuang; kunci harus 'gid:uid'."""
    _bersihkan_ekonomi()
    economy._muat_saldo_ekonomi(
        {
            "balances": {
                "111:5": 100,
                "111:6": 0,  # nol -> dibuang
                "111:7": -5,  # negatif -> dibuang
                "111:8": "50",  # string angka -> diterima
                "rusak": 10,  # tanpa titik dua -> dibuang
                "a:b": 10,  # bukan angka -> dibuang
            }
        }
    )

    assert economy.balances == {"111:5": 100, "111:8": 50}


def test_muat_meta_ekonomi_membuang_non_dict():
    """Meta hanya menerima dict; streak negatif dijepit ke 0."""
    _bersihkan_ekonomi()
    economy._muat_meta_ekonomi(
        {
            "meta": {
                "111:5": {"last_earn": "1.5", "last_daily": 2, "daily_streak": -3},
                "111:6": "bukan-dict",
                "111:7": None,
            }
        }
    )

    assert set(economy.meta) == {"111:5"}
    assert economy.meta["111:5"]["last_earn"] == 1.5
    assert economy.meta["111:5"]["daily_streak"] == 0


def test_muat_toko_ekonomi_membuang_item_tanpa_nama():
    """Item tanpa nama / bukan-dict dibuang; harga minimal 1; nama dipotong 60."""
    _bersihkan_ekonomi()
    economy._muat_toko_ekonomi(
        {
            "shop": {
                "111": {
                    "a": {"name": "Peran VIP", "price": 0, "role_id": "9", "description": "d" * 300},
                    "b": {"name": "   "},  # nama kosong -> dibuang
                    "c": "bukan-dict",  # dibuang
                    "d": {"name": "N" * 100},  # nama dipotong
                },
                "bukan-angka": {"x": {"name": "Y"}},
            }
        }
    )

    assert set(economy.shop) == {111}
    toko = economy.shop[111]
    assert set(toko) == {"a", "d"}
    assert toko["a"]["price"] == 1  # harga 0 dinaikkan ke minimum
    assert toko["a"]["role_id"] == 9
    assert len(toko["a"]["description"]) == 200
    assert len(toko["d"]["name"]) == 60


def test_helper_ekonomi_tidak_melempar_untuk_masukan_aneh():
    """Jaring aman: nilai None / list / string tidak boleh melempar exception."""
    _bersihkan_ekonomi()
    for aneh in ({"guilds": None}, {"guilds": []}, {"guilds": "teks"}, {}):
        economy._muat_guild_ekonomi(aneh)
    for aneh in ({"balances": None}, {"balances": []}, {}):
        economy._muat_saldo_ekonomi(aneh)
    for aneh in ({"meta": None}, {"meta": []}, {}):
        economy._muat_meta_ekonomi(aneh)
    for aneh in ({"shop": None}, {"shop": []}, {}):
        economy._muat_toko_ekonomi(aneh)

    assert economy.economy_guilds == {}
    assert economy.balances == {}


# ==============================================================================
# server_features.py
# ==============================================================================
def test_muat_serverstats_dasar():
    """Entri aktif dimuat; entri nonaktif dilewati."""
    _bersihkan_server_features()
    sf._muat_serverstats(
        {
            "serverstats": {
                "111": {"enabled": True, "category_id": 5, "channel_type": "voice"},
                "222": {"enabled": False},
            }
        }
    )

    assert set(sf.serverstats_guilds) == {111}
    stats = sf.serverstats_guilds[111]
    assert stats["enabled"] is True
    assert stats["category_id"] == 5
    assert stats["channel_type"] == "voice"


def test_muat_serverstats_membuang_tipe_channel_asing_dan_emoji_asing():
    """channel_type di luar daftar kembali ke 'voice'; emoji kunci asing dibuang."""
    _bersihkan_server_features()
    kunci_sah = {key for key, _, _ in sf.STATS_CHANNEL_SPECS}
    sf._muat_serverstats(
        {
            "serverstats": {
                "111": {
                    "channel_type": "ngawur",
                    "emojis": {"kunci-asing": "X", **{k: "🔥" for k in list(kunci_sah)[:1]}},
                }
            }
        }
    )

    stats = sf.serverstats_guilds[111]
    assert stats["channel_type"] == "voice"
    assert "kunci-asing" not in stats["emojis"]
    assert all(k in kunci_sah for k in stats["emojis"])


def test_muat_serverstats_membuang_entri_rusak():
    """gid non-angka dan nilai bertipe salah dilewati tanpa exception."""
    _bersihkan_server_features()
    sf._muat_serverstats(
        {
            "serverstats": {
                "bukan-angka": {"enabled": True},
                "222": {"last_update_at": "bukan-angka-temporal"},
                "333": "bukan-dict",
            }
        }
    )

    assert set(sf.serverstats_guilds) == set()


def test_muat_autorole_membuang_role_nol_dan_membatasi_jumlah():
    """Role id 0 dibuang; jumlah dibatasi AUTOROLE_MAX_ROLES."""
    _bersihkan_server_features()
    banyak = [str(i) for i in range(1, sf.AUTOROLE_MAX_ROLES + 20)]
    sf._muat_autorole(
        {
            "autorole": {
                "111": {"role_ids": [1, 0, "2", "x"], "include_bots": True},
                "222": {"role_ids": []},  # kosong -> dilewati
                "333": {"role_ids": banyak},
                "444": {"enabled": False},
            }
        }
    )

    assert set(sf.autorole_guilds) == {111, 333}
    assert sf.autorole_guilds[111]["role_ids"] == [1, 2]
    assert sf.autorole_guilds[111]["include_bots"] is True
    assert len(sf.autorole_guilds[333]["role_ids"]) <= sf.AUTOROLE_MAX_ROLES


def test_muat_facts_membuang_entri_nonaktif():
    """Fakta nonaktif tidak dimuat; yang aktif memakai _parse_facts_guild_config."""
    _bersihkan_server_features()
    sf._muat_facts(
        {
            "facts": {
                "111": {"enabled": True},
                "222": {"enabled": False},
            }
        }
    )

    assert set(sf.facts_guilds) <= {111}
    assert 222 not in sf.facts_guilds


def test_muat_security_action_asing_kembali_ke_bawaan():
    """Aksi phising di luar daftar kembali ke 'hapus_peringat'."""
    _bersihkan_server_features()
    sf._muat_security(
        {
            "security": {
                "111": {"action": "hapus", "channel_ids": [1, 0, "2"], "strict": True, "blocked": 9},
                "222": {"action": "ngawur"},
                "333": {"enabled": False},
            }
        }
    )

    assert set(sf.security_guilds) == {111, 222, 333}
    assert sf.security_guilds[111]["action"] == "hapus"
    assert sf.security_guilds[111]["channel_ids"] == [1, 2]
    assert sf.security_guilds[111]["strict"] is True
    assert sf.security_guilds[111]["blocked"] == 9

    assert sf.security_guilds[222]["action"] == "hapus_peringat"
    assert sf.security_guilds[333]["enabled"] is False


def test_helper_server_features_tidak_melempar_untuk_masukan_aneh():
    """Jaring aman untuk nilai None / list / string."""
    _bersihkan_server_features()
    for aneh in ({"serverstats": None}, {"serverstats": []}, {}):
        sf._muat_serverstats(aneh)
    for aneh in ({"autorole": None}, {"autorole": []}, {}):
        sf._muat_autorole(aneh)
    for aneh in ({"facts": None}, {"facts": []}, {}):
        sf._muat_facts(aneh)
    for aneh in ({"security": None}, {"security": []}, {}):
        sf._muat_security(aneh)

    assert sf.serverstats_guilds == {}
    assert sf.autorole_guilds == {}
    assert sf.facts_guilds == {}
    assert sf.security_guilds == {}
