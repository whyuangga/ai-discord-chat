"""Semua handler HTTP dashboard (halaman, API, berkas).

Dulu 29 handler ini adalah fungsi bersarang di dalam `start_dashboard()` —
satu fungsi 1.570 baris yang mustahil dibaca utuh. Sekarang mereka menjadi
method `RuteDashboard`; `start_dashboard()` tinggal merakit objek, tabel rute,
dan `aiohttp.Application`.

Konvensi pemanggilan internal:
- `self.bot`     — instance bot Discord
- `self.cfg`     — hasil `dashboard_config()`
- `self.helper`  — `HelperRespons` (payload, izin, redirect, sesi)
"""

from __future__ import annotations

import logging

from aiohttp import web

import analytics_export
import dashboard_admin
import dashboard_ai
import dashboard_bangun
import dashboard_curhat
import dashboard_form_inbox
import dashboard_giveaway
import dashboard_highlights
import dashboard_info
import dashboard_keamanan
import dashboard_lencana
import dashboard_moderasi
import dashboard_panel
import dashboard_pesan
import dashboard_snipe
import dashboard_security
import dashboard_sosial
import dashboard_stats
import dashboard_tags
import dashboard_tiket
import dashboard_ui
import dashboard_uji
import dashboard_unggah
import dashboard_voice
import ticket_archive
from web_dashboard import (  # inti: token, data, perakitan halaman
    _guild_hint,
    apply_dashboard_action,
    collect_features,
    collect_levels,
    collect_status,
    collect_tren,
    collect_usage,
    dashboard_controls,
    render_controls_block,
    render_dashboard_html,
    render_features_block,
)
from web_dashboard.halaman import (
    COOKIE_AUTO,
    COOKIE_AUTO_MAKS,
    FIELD_AUTO_MANUAL,
    GRUP_HALAMAN,
    HALAMAN_SLUG,
    LEGACY_HALAMAN,
    SETELAN_BOOST,
    SETELAN_PERPISAHAN,
    SETELAN_SAMBUTAN,
    UJI_HALAMAN,
    _anchor_aksi,
    _anchor_konten,
    _id_aman,
    detik_auto,
    detik_dari_kueri,
    fitur_grup,
    halaman_dari_path,
    url_halaman,
)

logger = logging.getLogger("gemini_bot.web_dashboard.rute")


def _401():
    """Balasan untuk permintaan tanpa token/sesi yang sah."""
    return web.Response(text="401 Unauthorized — tambahkan ?token=...", status=401)


def _redirect(tujuan: str):
    """303 See Other — POST/GET lama selesai, browser pindah ke `tujuan`."""
    return web.Response(status=303, headers={"Location": tujuan})


def _blok(pembuat, bawaan: str) -> str:
    """Gambar satu blok panel; kegagalan satu blok tidak mematikan halaman."""
    try:
        return pembuat()
    except Exception as exc:  # pragma: no cover - jaring aman per panel
        logger.warning("Blok dashboard gagal dirender: %s", exc)
        return bawaan


def _gid_dari(payload: dict, bot, request) -> int:
    """Server tujuan aksi: dari body (`guild`), jatuh ke query/pilih pertama."""
    raw = str((payload or {}).get("guild") or "").strip()
    return int(raw) if raw.isdigit() else _guild_hint(bot, request)[0]


def _nilai_setelan(gid: int) -> dict:
    """Nilai setelan server; gagal baca tidak boleh menjatuhkan halaman."""
    try:
        return dashboard_admin.read_values(gid)
    except Exception as exc:  # pragma: no cover - jaring aman
        logger.warning("Nilai setelan gagal dibaca: %s", exc)
        return {}



class RuteDashboard:
    """Kumpulan handler; satu instance per server dashboard yang menyala."""

    def __init__(self, bot, cfg: dict, helper, pembatas) -> None:
        self.bot = bot
        self.cfg = cfg
        self.helper = helper
        self.pembatas = pembatas


    async def handle_logout(self, request):
        """Logout: hapus cookie sesi lalu kembali ke halaman terkunci."""
        cookie = str(request.cookies.get(dashboard_security.NAMA_COOKIE_SESI) or "")
        if cookie:
            dashboard_security.hapus_sesi(cookie)
        respons = web.Response(status=303, headers={"Location": "/"})
        respons.del_cookie(dashboard_security.NAMA_COOKIE_SESI, path="/")
        return respons

    async def handle_status(self, request):
        if not self.helper.authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response(collect_status(self.bot))

    async def handle_usage(self, request):
        if not self.helper.authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        gid, _name = _guild_hint(self.bot, request)
        return web.json_response(collect_usage(gid))

    async def handle_levels(self, request):
        if not self.helper.authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        gid, _name = _guild_hint(self.bot, request)
        return web.json_response(collect_levels(gid))

    async def handle_kontrol(self, request):
        if not self.helper.authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        gid, guild_name = _guild_hint(self.bot, request)
        return web.json_response({"guild": gid, "guild_name": guild_name,
                                  "controls": dashboard_controls(gid)})

    def _pasang_sesi_dari_payload(self, request, payload: dict, respons):
        """POST dengan token di body (form HTML) juga mendapat cookie sesi.

        Ini menjaga alur `menu → form → POST` tetap jalan saat token belum
        pernah ditukar di URL. Token asli tidak pernah ditulis ke respons.
        """
        if str((payload or {}).get("token") or "").strip():
            return self.helper.pasang_sesi(request, respons)
        return respons

    async def handle_aksi(self, request):
        """Ubah setelan. Body JSON atau form HTML (token boleh di body)."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await self.helper.payload(request)
        request["_dash_payload"] = payload
        galat_body = self.helper.galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not self.helper.izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(self.bot, request)[0]
        aksi = str(payload.get("action") or "").strip()
        nilai = str(payload.get("value") or "")

        if aksi.lower().startswith("set."):
            kunci = aksi[4:]
            ok, message = await dashboard_admin.apply(gid, kunci, dashboard_admin.normalisasi(kunci, nilai))
        else:
            ok, message = await apply_dashboard_action(gid, aksi, nilai)
        logger.info("Dashboard aksi %s=%s (server %s): %s", aksi, nilai, gid, message)
        # Pengguna yang mengirim dari panel tertentu kembali ke panel itu; kalau
        # tidak, tebak dari aksi (mis. `set.welcome.*` → kartu sambutan).
        return self.helper.jawab(gid, ok, message, _anchor_aksi(aksi), request)

    async def handle_kirim(self, request):
        """Kirim pesan/embed ke channel (opsional lewat identitas webhook)."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await self.helper.payload(request)
        galat_body = self.helper.galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not self.helper.izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(self.bot, request)[0]
        banner, galat_banner, nama_banner = dashboard_unggah.siapkan(
            gid, payload.get("banner"), str(payload.get("banner_tersimpan") or "")
        )
        if galat_banner:
            return self.helper.kembali(gid, galat_banner, "p-kirim", ok=False)

        # Tombol "Pratinjau" (name=pratinjau) menampilkan hasil tanpa mengirim.
        if str(payload.get("pratinjau") or "").strip():
            data = dashboard_pesan.pratinjau(self.bot, gid, payload, banner=banner)
            logger.info("Dashboard pratinjau embed (server %s) ke %s", gid, data.get("channel_label"))
            if str(request.content_type or "").startswith("application/json"):
                return web.json_response({"ok": True, "pratinjau": data, "guild": gid})
            isian = {k: str(v) for k, v in payload.items() if k not in ("token", "pratinjau")}
            isian["token"] = self.cfg["token"]
            isian["guild"] = str(gid)
            isian["action"] = "kirim"
            if nama_banner:
                isian["banner_tersimpan"] = nama_banner
            halaman = dashboard_ui.render_pratinjau_html(
                pratinjau=data, token=self.cfg["token"], guild_id=gid, fields=isian
            )
            return web.Response(text=halaman, content_type="text/html", charset="utf-8")

        ok, message = await dashboard_pesan.kirim(self.bot, gid, payload, banner=banner)
        logger.info("Dashboard kirim (server %s): %s", gid, message)
        return self.helper.jawab(gid, ok, message, "p-kirim", request)

    async def handle_konten(self, request):
        """Buat / hapus konten: `action=buat.<jenis>` atau `hapus.<jenis>:<id>`.

        Dispatch dipecah per kelompok agar tiap cabang tetap terbaca utuh:
        `_aksi_konten` (buat/jeda), `_aksi_panel_konten` (stats/inbox/tag/…),
        dan `_aksi_banner` (banner panel + hapus).
        """
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await self.helper.payload(request)
        galat_body = self.helper.galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not self.helper.izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        gid = _gid_dari(payload, self.bot, request)
        aksi = str(payload.get("action") or "").strip().lower()

        for penangan in (self._aksi_konten, self._aksi_panel_konten, self._aksi_banner):
            hasil = await penangan(gid, aksi, payload)
            if isinstance(hasil, web.Response):     # cabang yang perlu redirect khusus
                return hasil
            if hasil is not None:
                ok, message = hasil
                break
        else:
            ok, message = False, f"Aksi konten `{aksi or '-'}` tidak dikenal."

        logger.info("Dashboard konten %s (server %s): %s", aksi, gid, message)
        return self.helper.jawab(gid, ok, message, _anchor_konten(aksi), request)

    async def _aksi_konten(self, gid: int, aksi: str, payload: dict):
        """`buat.*` (pengumuman, tautan, panel, formulir, pemicu) dan `jeda.*`."""
        if aksi == "buat.pengumuman":
            return await dashboard_pesan.tambah_pengumuman(gid, payload)
        if aksi == "buat.tautan":
            return await dashboard_pesan.tambah_tautan(gid, payload)
        if aksi == "buat.panel":
            banner, galat_banner, _nama = dashboard_unggah.siapkan(
                gid, payload.get("banner"), str(payload.get("banner_tersimpan") or "")
            )
            if galat_banner:
                return self.helper.kembali(gid, galat_banner, "p-buat", ok=False)
            return await dashboard_pesan.buat_panel(self.bot, gid, payload, banner=banner)
        if aksi == "buat.formulir":
            return await dashboard_pesan.tambah_formulir(gid, payload)
        if aksi == "buat.pemicu":
            return await dashboard_pesan.pasang_pemicu(gid, payload)
        if aksi.startswith("jeda."):
            return await self._aksi_jeda(gid, aksi)
        return None

    async def _aksi_jeda(self, gid: int, aksi: str):
        """Jeda/lanjutkan pengumuman (`jeda.pengumuman:<id>`)."""
        import engagement

        jenis, _, ref = aksi[len("jeda."):].partition(":")
        if jenis != "pengumuman":
            return False, f"Jenis `{jenis or '-'}` tidak bisa dijeda."
        data_pengumuman = engagement.announcements.get(int(ref)) if ref.isdigit() else None
        if data_pengumuman is None:
            return False, "Pengumuman tidak ditemukan."
        return await dashboard_pesan.ubah_pengumuman(
            gid, int(ref), not bool(data_pengumuman.get("enabled", True))
        )

    async def _aksi_panel_konten(self, gid: int, aksi: str, payload: dict):
        """Panel konten non-pesan: stats, inbox, info, voice, sosial, curhat, tag, starboard."""
        if aksi.startswith("stats-"):
            return await dashboard_stats.aksi_stats(gid, aksi, payload)
        if aksi.startswith("inbox-"):
            return await dashboard_form_inbox.aksi_inbox(gid, aksi, payload)
        if aksi.startswith("info-"):
            return await dashboard_info.aksi_info(self.bot, gid, aksi, payload)
        if aksi.startswith("voice-"):
            return await dashboard_voice.aksi_voice(self.bot, gid, aksi, payload)
        if aksi.startswith("sosial-"):
            return await dashboard_sosial.aksi_sosial(gid, aksi, payload)
        if aksi.startswith("curhat-"):
            return await dashboard_curhat.aksi_curhat(gid, aksi, payload)
        if aksi.startswith("pantau-"):
            return await dashboard_highlights.aksi_highlights(gid, aksi, payload)
        if aksi.startswith("tag-"):
            return await self._aksi_tag(gid, aksi, payload)
        if aksi.startswith("starboard-"):
            return await self._aksi_starboard(gid, aksi, payload)
        return None

    async def _aksi_tag(self, gid: int, aksi: str, payload: dict):
        """Simpan / hapus / aktifkan tag server."""
        import tags

        if aksi == "tag-simpan":
            ok, message = dashboard_tags.simpan_tag(gid, payload)
            if ok:
                await tags.save_tags_to_disk()
            return ok, message
        if aksi.startswith("tag-hapus:"):
            nama = aksi.split(":", 1)[1]
            ok = tags.hapus(gid, nama)
            if ok:
                await tags.save_tags_to_disk()
            return ok, (
                f"Tag `{tags.normalisasi(nama)}` dihapus." if ok
                else f"Tidak ada tag bernama `{nama}`."
            )
        if aksi.startswith("tag-aktif:"):
            hidup = aksi.split(":", 1)[1].strip() not in ("0", "false", "off")
            tags.set_config(gid, enabled=hidup)
            await tags.save_tags_to_disk()
            return True, f"Tag {'diaktifkan' if hidup else 'dinonaktifkan'}."
        return None

    async def _aksi_starboard(self, gid: int, aksi: str, payload: dict):
        """Tambah/hapus papan sorotan (starboard)."""
        import community_tools

        if aksi == "starboard-tambah":
            ok, message = community_tools.add_starboard_board(
                gid,
                str(payload.get("nama") or ""),
                emoji=str(payload.get("emoji") or ""),
                threshold=_id_aman(payload.get("batas")),
                channel_id=_id_aman(payload.get("channel_id")),
                warna=str(payload.get("warna") or ""),
            )
            if ok:
                await community_tools.save_community_tools_to_disk()
            return ok, message
        if aksi.startswith("starboard-hapus:"):
            ok, message = community_tools.remove_starboard_board(gid, aksi.split(":", 1)[1])
            if ok:
                await community_tools.save_community_tools_to_disk()
            return ok, message
        return None

    async def _aksi_banner(self, gid: int, aksi: str, payload: dict):
        """Banner panel (`banner.panel:` / `hapusbanner.panel:`) dan `hapus.*`."""
        if aksi.startswith(("banner.panel:", "hapusbanner.panel:")):
            ref_panel = aksi.split(":", 1)[1]
            if aksi.startswith("hapusbanner."):
                return await dashboard_pesan.ganti_banner_panel(
                    self.bot, gid, ref_panel, banner=None
                )
            banner, galat_banner, _nama = dashboard_unggah.siapkan(
                gid, payload.get("banner"), str(payload.get("banner_tersimpan") or "")
            )
            if galat_banner:
                return self.helper.kembali(gid, galat_banner, "p-panel", ok=False)
            if banner is None:
                return self.helper.kembali(
                    gid, "Pilih berkas banner atau banner tersimpan lebih dulu.",
                    "p-panel", ok=False,
                )
            return await dashboard_pesan.ganti_banner_panel(
                self.bot, gid, ref_panel, banner=banner
            )
        if aksi.startswith("hapus."):
            jenis, _, ref = aksi[len("hapus."):].partition(":")
            return await dashboard_pesan.hapus(self.bot, gid, jenis, ref)
        return None

    async def handle_panel(self, request):
        """Editor panel: daftar item (GET) atau tambah/hapus item (POST)."""
        if request.method == "GET":
            if not self.helper.authorized(request):
                return web.json_response({"error": "unauthorized"}, status=401)
            gid, _name = _guild_hint(self.bot, request)
            return web.json_response(dashboard_panel.collect_panel(gid))

        payload = await self.helper.payload(request)
        galat_body = self.helper.galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not self.helper.izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(self.bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()
        jenis, _, ref = aksi.partition(":")

        if jenis == "tambah":
            ok, message = await dashboard_panel.tambah_item(
                self.bot, gid, {**payload, "panel": ref}
            )
        elif jenis == "verifikasi" and ref.strip().lower() == "matikan":
            ok, message = await dashboard_panel.matikan_verifikasi(gid)
        elif jenis == "verifikasi":
            ok, message = await dashboard_panel.pasang_verifikasi(self.bot, gid, payload)
        elif jenis == "hapus":
            panel_id, _, item_ref = ref.partition(":")
            ok, message = await dashboard_panel.hapus_item(
                self.bot, gid, {**payload, "panel": panel_id, "item": item_ref}
            )
        else:
            ok, message = False, f"Aksi panel `{aksi or '-'}` tidak dikenal."
        logger.info("Dashboard panel %s (server %s): %s", aksi, gid, message)
        return self.helper.jawab(gid, ok, message, "p-panel", request)

    async def simpan_tiket(self, ) -> None:
        """Simpan perubahan konfigurasi tiket (topik) ke `data/tickets.json`."""
        import tickets

        try:
            await tickets.save_tickets_to_disk()
        except Exception as exc:  # pragma: no cover - I/O gagal
            logger.warning("Gagal menyimpan konfigurasi tiket: %s", exc)

    async def handle_keamanan(self, request):
        """POST penguji aturan anti-spam (tanpa menindak apa pun)."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await self.helper.payload(request)
        galat_body = self.helper.galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not self.helper.izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(self.bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()

        if aksi == "honeypot-simpan":
            import honeypot

            cid = _id_aman(payload.get("channel_id"))
            lama = honeypot.status(gid)
            ids = list(lama["channel_ids"])
            if cid and cid not in ids:
                ids.append(cid)
            ok, message = True, ""
            honeypot.set_honeypot(
                gid,
                channel_ids=ids,
                aksi=str(payload.get("aksi") or ""),
                timeout_sec=_id_aman(payload.get("timeout_sec")) or None,
                log_channel_id=_id_aman(payload.get("log_channel_id")),
                abaikan_staf=str(payload.get("abaikan_staf") or "1") not in ("0", "false", "off"),
            )
            await honeypot.save_honeypot_to_disk()
            data = honeypot.status(gid)
            message = (
                f"Honeypot disimpan: channel {', '.join(f'#{c}' for c in data['channel_ids'])} · "
                f"tindakan {data['label_aksi']}."
                if data["channel_ids"]
                else "Honeypot disimpan, tapi belum ada channel jebakan yang dipilih."
            )
        elif aksi == "honeypot-hapus":
            import honeypot

            ok = honeypot.clear_honeypot(gid)
            if ok:
                await honeypot.save_honeypot_to_disk()
            message = (
                "Honeypot dimatikan & setelannya dihapus."
                if ok
                else "Belum ada setelan honeypot untuk dihapus."
            )
        elif aksi == "uji-aturan":
            ok, message = dashboard_keamanan.uji(
                gid, str(payload.get("teks") or ""), ulang=_id_aman(payload.get("ulang"))
            )
        else:
            ok, message = False, f"Aksi keamanan `{aksi or '-'}` tidak dikenal."
        logger.info("Dashboard keamanan %s (server %s): %s", aksi, gid, message)
        return self.helper.jawab(gid, ok, message, "p-aturan", request)

    async def handle_lencana(self, request):
        """Panel lencana: setelan, role hadiah, & hapus hadiah."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await self.helper.payload(request)
        galat_body = self.helper.galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not self.helper.izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(self.bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()

        ok, message = await dashboard_lencana.aksi_lencana(gid, aksi, payload)
        logger.info("Dashboard lencana %s (server %s): %s", aksi, gid, message)
        return self.helper.jawab(gid, ok, message, "p-lencana", request)

    async def handle_moderasi(self, request):
        """Panel moderasi: setelan laporan, ubah status antrean, cari kasus, cabut temp-ban."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await self.helper.payload(request)
        galat_body = self.helper.galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not self.helper.izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        import moderation
        import reports

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(self.bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()
        anchor = "p-moderasi"

        if aksi == "laporan-setelan":
            cid = _id_aman(payload.get("channel_id"))
            reports.set_config(
                gid,
                channel_id=cid or None,
                cooldown_sec=_id_aman(payload.get("cooldown_sec")),
                enabled=str(payload.get("enabled") or "1") not in ("0", "false", "off"),
                dm_pelapor=str(payload.get("dm_pelapor") or "1") not in ("0", "false", "off"),
            )
            await reports.save_reports_to_disk()
            data = reports.status(gid)
            ok, message = True, (
                f"Setelan laporan disimpan: {'aktif' if data['aktif'] else 'nonaktif'} · "
                f"cooldown {data['cooldown_sec']} detik · channel "
                f"{'#' + str(data['channel_id']) if data['channel_id'] else 'ikut log moderasi'}."
            )
        elif aksi == "antrean-status":
            kode = _id_aman(payload.get("kode"))
            entri = reports.ubah_status(
                gid, kode, str(payload.get("status") or ""),
                catatan=str(payload.get("catatan") or ""),
            )
            if entri is None:
                ok, message = False, f"Antrean `#{kode}` tidak ditemukan atau status tidak valid."
            else:
                await reports.save_reports_to_disk()
                ok, message = True, (
                    f"Antrean `#{kode}` → {reports.STATUS.get(entri['status'], entri['status'])}."
                )
        elif aksi == "tempban-cabut":
            uid = _id_aman(payload.get("user_id"))
            dicabut = moderation.drop_tempban(gid, uid)
            if not dicabut:
                ok, message = False, f"Tidak ada temp-ban aktif untuk `{uid}`."
            else:
                await moderation.save_moderation_to_disk()
                ok, message = True, (
                    f"Temp-ban `{uid}` dicabut dari daftar tunggu. Bila ban masih aktif, "
                    "cabut lewat `/mod unban user_id:" + str(uid) + "`."
                )
        elif aksi == "cari-kasus":
            hasil = dashboard_moderasi.cari_kasus(
                gid, str(payload.get("q") or ""), str(payload.get("aksi") or "")
            )
            ok, message = True, (
                f"{len(hasil)} kasus ditemukan."
                if hasil
                else "Tidak ada kasus yang cocok dengan pencarian itu."
            )
        else:
            ok, message = False, f"Aksi moderasi `{aksi or '-'}` tidak dikenal."
        logger.info("Dashboard moderasi %s (server %s): %s", aksi, gid, message)
        return self.helper.jawab(gid, ok, message, anchor, request)

    async def handle_tiket(self, request):
        """Kotak masuk tiket: daftar (GET) atau balas/tutup (POST)."""
        if request.method == "GET":
            if not self.helper.authorized(request):
                return web.json_response({"error": "unauthorized"}, status=401)
            gid, _name = _guild_hint(self.bot, request)
            return web.json_response(dashboard_tiket.collect_tiket(gid))

        payload = await self.helper.payload(request)
        galat_body = self.helper.galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not self.helper.izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(self.bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()
        jenis, _, ref = aksi.partition(":")

        if jenis == "balas":
            ok, message = await dashboard_tiket.balas(
                self.bot, gid, ref, str(payload.get("teks") or ""),
                identitas=str(payload.get("identitas") or ""),
            )
        elif jenis == "tutup":
            ok, message = await dashboard_tiket.tutup(self.bot, gid, ref)
        elif jenis == "topik-tambah":
            ok, message = dashboard_tiket.topik_tambah(
                gid,
                str(payload.get("nama") or ""),
                role_id=_id_aman(payload.get("role_id")),
                emoji=str(payload.get("emoji") or ""),
                deskripsi=str(payload.get("deskripsi") or ""),
            )
            if ok:
                await self.simpan_tiket()
        elif jenis == "topik-hapus":
            ok, message = dashboard_tiket.topik_hapus(gid, str(payload.get("nama") or ""))
            if ok:
                await self.simpan_tiket()
        elif jenis == "catat":
            ok, message = dashboard_tiket.catat(
                gid, _id_aman(ref), str(payload.get("teks") or "")
            )
        elif jenis == "catatan-hapus":
            tid_str, _, nomor = ref.partition(":")
            ok, message = dashboard_tiket.hapus_catatan(gid, _id_aman(tid_str), _id_aman(nomor))
        elif jenis == "panel":
            ok, message = await dashboard_tiket.pasang_panel(self.bot, gid, payload)
        elif jenis == "matikan":
            ok, message = await dashboard_tiket.matikan_tiket(gid)
        else:
            ok, message = False, f"Aksi tiket `{aksi or '-'}` tidak dikenal."
        logger.info("Dashboard tiket %s (server %s): %s", aksi, gid, message)
        return self.helper.jawab(gid, ok, message, "p-tiket", request)

    async def handle_transkrip(self, request):
        """Halaman arsip transkrip tiket + pencarian (tanpa JavaScript)."""
        if not self.helper.authorized(request):
            return web.Response(
                text="401 Unauthorized — tambahkan ?token=...", status=401
            )
        gid, guild_name = _guild_hint(self.bot, request)
        kata = str(request.query.get("q") or "").strip()[:80]
        hasil = (
            ticket_archive.cari(gid, kata, limit=30)
            if kata
            else ticket_archive.daftar(gid, limit=30)
        )
        page = dashboard_ui.render_halaman_arsip(
            gid,
            self.cfg["token"],
            kata=kata,
            hasil=hasil,
            stat=ticket_archive.statistik(gid),
            nama_server=guild_name,
        )
        return web.Response(
            text=page,
            content_type="text/html",
            charset="utf-8",
            headers={"X-Robots-Tag": "noindex"},
        )

    async def handle_transkrip_berkas(self, request):
        """Berkas transkrip HTML satu tiket (GET) atau hapus arsip (POST)."""
        if request.method == "GET":
            if not self.helper.authorized(request):
                return web.json_response({"error": "unauthorized"}, status=401)
            gid, _name = _guild_hint(self.bot, request)
            kode = str(request.query.get("kode") or "").strip()
            isi = ticket_archive.baca_html(gid, kode)
            if isi is None:
                return web.Response(
                    text="Arsip transkrip tidak ditemukan (mungkin sudah dihapus).",
                    status=404,
                    content_type="text/plain",
                    charset="utf-8",
                )
            return web.Response(
                text=isi,
                content_type="text/html",
                charset="utf-8",
                headers={"X-Robots-Tag": "noindex", "Cache-Control": "no-store"},
            )

        payload = await self.helper.payload(request)
        galat_body = self.helper.galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not self.helper.izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(self.bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()
        if aksi == "hapus":
            ok = ticket_archive.hapus(gid, str(payload.get("kode") or "").strip())
            pesan = (
                f"Arsip transkrip #{payload.get('kode')} dihapus."
                if ok
                else "Arsip transkrip itu tidak ditemukan."
            )
        else:
            ok, pesan = False, f"Aksi arsip `{aksi or '-'}` tidak dikenal."
        try:
            await dashboard_admin.audit_append(
                gid, f"transkrip.{aksi or '-'}", str(payload.get("kode") or "")[:40],
                ok=ok, pesan=pesan,
            )
        except Exception as exc:  # pragma: no cover - audit opsional
            logger.debug("Efek samping opsional gagal: %s", exc)
        logger.info("Dashboard transkrip %s (server %s): %s", aksi, gid, pesan)
        return self.helper.jawab(gid, ok, pesan, "p-tiket", request)

    async def handle_giveaway(self, request):
        """Kendali giveaway: daftar (GET) atau aksi buat/akhiri/reroll/template (POST)."""
        if request.method == "GET":
            if not self.helper.authorized(request):
                return web.json_response({"error": "unauthorized"}, status=401)
            gid, _name = _guild_hint(self.bot, request)
            return web.json_response(dashboard_giveaway.collect(gid))

        payload = await self.helper.payload(request)
        galat_body = self.helper.galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not self.helper.izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(self.bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()
        try:
            ok, pesan = await dashboard_giveaway.aksi(self.bot, gid, aksi, payload)
        except Exception as exc:  # pragma: no cover - jaring aman
            logger.warning("Aksi giveaway gagal: %s", exc)
            ok, pesan = False, "Aksi giveaway gagal dijalankan."

        nama_aksi = aksi.partition(":")[0] or "-"
        try:
            await dashboard_admin.audit_append(
                gid,
                f"giveaway.{nama_aksi}",
                str(payload.get("hadiah") or payload.get("nama") or aksi)[:120],
                ok=ok,
                pesan=pesan,
            )
        except Exception as exc:  # pragma: no cover - audit opsional
            logger.debug("Efek samping opsional gagal: %s", exc)
        logger.info("Dashboard giveaway %s (server %s): %s", aksi, gid, pesan)
        return self.helper.jawab(gid, ok, pesan, "p-giveaway", request)

    async def handle_ekspor(self, request):
        """Unduh CSV analitik server (level/moderasi/tiket/pemakaian)."""
        if not self.helper.authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)

        gid, _name = _guild_hint(self.bot, request)
        jenis = str(request.query.get("jenis") or "level").strip().lower()
        isi, nama_berkas, galat = analytics_export.build_csv(jenis, gid)
        if isi is None:
            return web.Response(
                text=galat or "Data belum tersedia.", status=404,
                content_type="text/plain", charset="utf-8",
            )
        return web.Response(
            body=analytics_export.csv_bytes(isi),
            content_type="text/csv",
            charset="utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nama_berkas}"'},
        )

    async def handle_unggah(self, request):
        """Simpan / hapus banner. Multipart untuk berkas, form biasa untuk hapus."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await self.helper.payload(request)
        galat_body = self.helper.galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not self.helper.izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(self.bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()

        if aksi == "unggah.simpan":
            berkas, galat, nama = dashboard_unggah.siapkan(gid, payload.get("banner"))
            if galat:
                ok, message = False, galat
            elif not nama:
                ok, message = False, "Pilih berkas gambar lebih dulu."
            else:
                ok, message = True, f"Banner tersimpan: `{nama}`."
        elif aksi.startswith("kartu.simpan:"):
            ok, message = dashboard_unggah.simpan_kartu(
                gid, payload.get("banner"), aksi.split(":", 1)[1]
            )
        elif aksi.startswith("kartu.hapus:"):
            ok, message = dashboard_unggah.hapus_kartu(gid, aksi.split(":", 1)[1])
        elif aksi.startswith("hapus.banner:"):
            nama = aksi.split(":", 1)[1]
            ok = dashboard_unggah.hapus(gid, nama)
            message = f"Banner `{nama}` dihapus." if ok else "Banner tidak ditemukan."
        else:
            ok, message = False, f"Aksi unggah `{aksi or '-'}` tidak dikenal."
        logger.info("Dashboard unggah %s (server %s): %s", aksi, gid, message)
        anchor = "p-banner"
        if aksi.startswith("kartu."):
            jenis = aksi.split(":", 1)[1] if ":" in aksi else ""
            anchor = {
                "welcome": "p-sambutan",
                "goodbye": "p-perpisahan",
                "boost": "p-boost",
            }.get(jenis, "p-sambutan")
        return self.helper.jawab(gid, ok, message, anchor, request)

    async def handle_bangun(self, request):
        """Pratinjau, terapkan, atau bongkar item `/bangun` (token dashboard wajib)."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await self.helper.payload(request)
        galat_body = self.helper.galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not self.helper.izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(self.bot, request)[0]
        aksi = str(payload.get("action") or payload.get("aksi") or "-").strip().lower()
        try:
            ok, message = await dashboard_bangun.proses_aksi(self.bot, gid, payload)
        except Exception as exc:  # pragma: no cover - kegagalan Discord/API tak terduga
            logger.warning("Dashboard bangun %s gagal (server %s): %s", aksi, gid, exc)
            ok, message = False, f"Aksi gagal ({type(exc).__name__}); pratinjau tetap aman."

        # Catat perubahan tanpa menyimpan deskripsi bebas yang dikirim ke perancang AI.
        if aksi == "tema":
            nilai_audit = f"tema:{str(payload.get('tema') or '')[:40]}"
        elif aksi == "rancang":
            nilai_audit = f"deskripsi {len(str(payload.get('deskripsi') or ''))} huruf (isi tidak dicatat)"
        elif aksi == "terapkan":
            nilai_audit = "rencana pratinjau"
        elif aksi == "bongkar":
            nilai_audit = "item tercatat" if str(payload.get("konfirmasi") or "") == "ya" else "konfirmasi belum dicentang"
        else:
            nilai_audit = aksi
        await dashboard_admin.audit_append(
            gid, f"bangun.{aksi}"[:64], nilai_audit, ok=ok, pesan=message
        )
        logger.info("Dashboard bangun aksi %s (server %s): %s", aksi, gid, message)
        return self.helper.jawab(gid, ok, message, "p-bangun", request)

    async def handle_ai(self, request):
        """Buat gambar di Discord atau simpan prompt kepribadian AI server."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await self.helper.payload(request)
        galat_body = self.helper.galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not self.helper.izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(self.bot, request)[0]
        aksi = str(payload.get("action") or payload.get("aksi") or "-").strip().lower()
        try:
            ok, message = await dashboard_ai.proses_aksi(self.bot, gid, payload)
        except Exception as exc:  # pragma: no cover - kegagalan Discord/API tak terduga
            logger.warning("Dashboard AI %s gagal (server %s): %s", aksi, gid, type(exc).__name__)
            ok, message = False, f"Aksi AI gagal ({type(exc).__name__})."

        # Audit hanya metadata; prompt dan isi gambar/lampiran tidak pernah dicatat.
        if aksi == "gambar":
            nilai_audit = (
                f"channel={_id_aman(payload.get('channel_id'))}; "
                f"gaya={str(payload.get('style') or 'channel')[:32]}; "
                f"rasio={str(payload.get('ratio') or 'channel')[:32]}; "
                f"prompt {len(str(payload.get('prompt') or ''))} huruf"
            )
            anchor = "p-gambar"
        elif aksi == "prompt-server":
            nilai_audit = f"prompt {len(str(payload.get('prompt_server') or ''))} huruf (isi tidak dicatat)"
            anchor = "p-ai-settings"
        else:
            nilai_audit, anchor = aksi[:100], "p-ai"
        pesan_audit = (
            ("Gambar dibuat dan dikirim." if ok else "Gambar gagal; detail tidak disimpan di audit.")
            if aksi == "gambar" else message
        )
        await dashboard_admin.audit_append(
            gid, f"ai.{aksi}"[:64], nilai_audit[:180], ok=ok, pesan=pesan_audit[:180]
        )
        logger.info(
            "Dashboard AI %s (server %s): %s",
            aksi, gid, ("berhasil" if ok else "gagal") if aksi == "gambar" else message,
        )
        return self.helper.jawab(gid, ok, message, anchor, request)

    async def handle_uji(self, request):
        """Jalankan satu tes fitur. Subjek tes opsional — default pemilik server."""
        if request.method != "POST":
            return web.json_response({"error": "gunakan POST"}, status=405)
        payload = await self.helper.payload(request)
        galat_body = self.helper.galat_payload(payload)
        if galat_body is not None:
            return galat_body
        if not self.helper.izin(request, payload):
            return web.json_response({"error": "unauthorized"}, status=401)

        raw_guild = str(payload.get("guild") or "").strip()
        gid = int(raw_guild) if raw_guild.isdigit() else _guild_hint(self.bot, request)[0]
        aksi = str(payload.get("action") or "").strip().lower()
        kunci = aksi.split(":", 1)[1].strip() if ":" in aksi else aksi.removeprefix("uji.").strip()
        opsi = str(
            payload.get("opsi_manual") or payload.get("opsi") or payload.get("member") or ""
        ).strip()
        ok, message = await dashboard_uji.jalankan_uji(self.bot, gid, kunci, None, opsi)
        logger.info("Dashboard uji %s (server %s): %s", kunci, gid, message)
        anchor = dashboard_uji.ANCHOR_UJI.get(str(kunci).strip().lower(), "p-kontrol")
        return self.helper.jawab(gid, ok, message, anchor, request)

    async def handle_kartu(self, request):
        """Sajikan gambar kartu sambutan tersimpan (pratinjau di dashboard)."""
        if not self.helper.authorized(request):
            return web.Response(text="401 Unauthorized", status=401)
        jenis = str(request.match_info.get("jenis") or "")
        gid, _nama = _guild_hint(self.bot, request)
        isi, tipe = dashboard_unggah.baca_kartu(gid, jenis)
        if isi is None:
            return web.Response(text="404 Not Found", status=404)
        return web.Response(
            body=isi,
            content_type=tipe,
            headers={"Cache-Control": "private, max-age=60"},
        )

    async def handle_rank_png(self, request):
        """Kartu rank PNG untuk pratinjau dashboard (perender sama dengan /level kartu)."""
        if not self.helper.authorized(request):
            return web.Response(text="401 Unauthorized", status=401)

        import rank_card

        gid, _nama = _guild_hint(self.bot, request)
        member = _id_aman(request.query.get("member"))
        guild = None
        getter = getattr(self.bot, "get_guild", None)
        if callable(getter):
            guild = getter(gid)
        if not member and guild is not None:
            member = int(getattr(guild, "owner_id", 0) or 0)

        nama = "Member"
        avatar = None
        orang = None
        cari = getattr(guild, "get_member", None) if guild is not None else None
        if callable(cari) and member:
            try:
                orang = cari(member)
            except Exception:  # pragma: no cover - jaring aman
                orang = None
        if orang is not None:
            nama = getattr(orang, "display_name", "") or getattr(orang, "name", "") or nama
            avatar = await rank_card.baca_avatar(orang)

        data = rank_card.data_kartu(
            gid,
            member,
            nama=nama,
            guild_name=str(getattr(guild, "name", "") or ""),
        )
        isi = await rank_card.render_kartu(data, avatar_bytes=avatar)
        if not isi:
            return web.Response(
                text="Kartu rank tidak bisa dirender (Pillow tidak tersedia atau dimatikan).",
                status=503,
                content_type="text/plain",
            )
        unduh = str(request.query.get("unduh") or "") in ("1", "true", "ya")
        header = {
            "Cache-Control": "no-store",
            "Content-Disposition": (
                f'attachment; filename="kartu-rank-{member or 0}.png"'
                if unduh
                else f'inline; filename="kartu-rank-{member or 0}.png"'
            ),
        }
        return web.Response(body=isi, content_type="image/png", headers=header)

    async def handle_berkas(self, request):
        """Sajikan banner tersimpan untuk pratinjau di halaman dashboard."""
        if not self.helper.authorized(request):
            return web.Response(text="401 Unauthorized", status=401)
        nama = str(request.match_info.get("nama") or "")
        gid, _name = _guild_hint(self.bot, request)
        if not dashboard_unggah.berkuasa(gid, nama):
            return web.Response(text="404 Not Found", status=404)
        isi = dashboard_unggah.baca(gid, nama)
        if isi is None:
            return web.Response(text="404 Not Found", status=404)
        return web.Response(
            body=isi,
            content_type=dashboard_unggah.tipe(nama),
            headers={"Cache-Control": "private, max-age=300"},
        )

    async def handle_health(self, _request):
        """`/healthz` polos — tanpa token dan tanpa HTML, untuk uptime monitor."""
        return web.Response(text="ok", content_type="text/plain")

    async def handle_tren(self, request):
        if not self.helper.authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response(collect_tren(int(request.query.get("hari") or 7)))

    async def handle_setelan(self, request):
        """JSON semua setelan + nilai sekarang (untuk otomasi/tes)."""
        if not self.helper.authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        gid, guild_name = _guild_hint(self.bot, request)
        return web.json_response(
            {
                "guild": gid,
                "guild_name": guild_name,
                "ringkasan": dashboard_admin.ringkasan(),
                "nilai": dashboard_admin.read_values(gid),
                "riwayat": dashboard_admin.audit_terakhir(gid, limit=10),
            }
        )

    async def handle_features(self, request):
        if not self.helper.authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        gid, _name = _guild_hint(self.bot, request)
        return web.json_response(collect_features(gid))


class HalamanDashboard:
    """Rute halaman HTML (`/`, `/inti`, `/kirim`, …) — bagian terberat dashboard.

    Blok-blok panel dimuat lewat fungsi `render_*` di modul `dashboard_*`;
    kegagalan satu blok tidak mematikan seluruh halaman (lihat `_blok`).
    """

    def __init__(self, bot, cfg: dict, helper) -> None:
        self.bot = bot
        self.cfg = cfg
        self.helper = helper

    async def handle_index(self, request):
        """Satu handler untuk semua halaman HTML (`/`, `/inti`, `/ai`, …).

        Alurnya sengaja linier dan pendek; pekerjaan beratnya ada di method
        pembantu: redirect (bookmark lama & token), penyusunan blok panel, dan
        pemilihan blok yang relevan untuk halaman ini.
        """
        if not self.helper.authorized(request):
            return _401()
        gid, guild_name = _guild_hint(self.bot, request)

        redirect = self._siapkan_permintaan(request, gid)
        if redirect is not None:
            return redirect

        slug = halaman_dari_path(request.path)
        meta = HALAMAN_SLUG[slug]
        detik = detik_auto(request, self.cfg["refresh"])
        simpan_auto = str(request.cookies.get(COOKIE_AUTO) or "").strip()
        pilih_auto = simpan_auto if simpan_auto.isdigit() else "auto"
        if str(request.query.get("isi") or "").strip() == "1":
            pilih_auto = "manual"        # mode “✏️ Isi sendiri…” dibuka

        blok = self._susun_blok(slug, gid, slug_halaman=slug)
        tren = collect_tren(7)
        blok["tren_block"] = _blok(
            lambda: dashboard_ui.render_tren_svg(tren["rows"], judul="Operasi AI"),
            '<div class="muted">Belum ada data tren.</div>',
        )

        page = render_dashboard_html(
            status=collect_status(self.bot),
            usage=collect_usage(gid),
            levels=collect_levels(gid),
            refresh=detik,
            auto_aksi=f"/{slug}" if slug else "/",
            auto_dipilih=pilih_auto,
            heading=guild_name or "Bot",
            guild_picker=_blok(
                lambda: dashboard_ui.render_guild_picker(self.bot, gid, "", halaman=slug), ""
            ),
            alamat_bersih=url_halaman(slug, "", gid),
            flash_pesan=str(request.query.get("pesan") or "")[:300],
            flash_ok=str(request.query.get("ok") or "1") != "0",
            tren_hari=tren["hari"],
            halaman=slug,
            token="",
            guild_id=gid,
            judul_halaman=meta["judul"],
            keterangan=meta["keterangan"],
            **blok,
        )
        return web.Response(text=page, content_type="text/html", charset="utf-8")

    def _siapkan_permintaan(self, request, gid: int):
        """Redirect yang harus terjadi sebelum halaman dirender (atau `None`).

        Tiga hal ditangani berurutan karena saling memengaruhi:
        1. bookmark lama (`/?halaman=setelan`, `/uji`) → halaman barunya;
        2. auto-refresh (`?refresh=600` / `?refresh_detik=45`) → cookie;
        3. `?token=` → tukar jadi cookie sesi lalu buang dari URL.
        """
        pinta = str(request.query.get("halaman") or "").strip()
        lama = str(request.path or "").strip("/")
        if lama in LEGACY_HALAMAN and not pinta:
            return _redirect(url_halaman(LEGACY_HALAMAN[lama], "", gid))
        if pinta in LEGACY_HALAMAN:
            return _redirect(url_halaman(LEGACY_HALAMAN[pinta], "", gid))
        if pinta and pinta in HALAMAN_SLUG and request.path.strip("/") != pinta:
            return _redirect(url_halaman(pinta, "", gid))

        if "refresh" in request.query or FIELD_AUTO_MANUAL in request.query:
            return self._atur_auto(request, gid)

        if str(request.query.get("token") or "").strip():
            # Token tertinggal di riwayat browser, header `Referer`, dan access
            # log reverse proxy bila dibiarkan di URL.
            tujuan = self.helper.url_kembali_dari(request, self.helper.anchor_form(request))
            return _redirect(tujuan)
        return None

    def _atur_auto(self, request, gid: int):
        """Simpan pilihan auto-refresh di cookie (tanpa JavaScript, tanpa `.env`)."""
        nilai = detik_dari_kueri(request.query)
        balik = url_halaman(halaman_dari_path(request.path), "", gid)
        if "refresh" in balik or FIELD_AUTO_MANUAL in balik:
            balik = balik.split("?")[0] + f"?guild={gid}"
        if nilai == "manual":
            # “✏️ Isi sendiri…” dipilih tapi angkanya belum diisi: tampilkan
            # kotak angka (tanpa mengubah nilai yang sedang berlaku).
            return _redirect(balik + "&isi=1")
        jawab = _redirect(balik)
        if nilai == "auto":
            jawab.del_cookie(COOKIE_AUTO, path="/")
        else:
            jawab.set_cookie(
                COOKIE_AUTO, nilai,
                max_age=COOKIE_AUTO_MAKS, path="/", httponly=True, samesite="Lax",
            )
        return jawab

    def _blok_opsional(self, gid: int) -> dict:
        """Panel fitur yang hanya muncul di beberapa halaman (tag, snipe, AI, …).

        Semua dipetakan sebagai data supaya menambah panel baru cukup satu baris
        dan tidak ada lagi deretan 25 `_blok(lambda: …)` yang seragam.
        """
        token = ""
        peta = {
            "kartu_rank_block": lambda: dashboard_ui.render_kartu_rank_block(self.bot, gid, token),
            "honeypot_block": lambda: dashboard_ui.render_honeypot_block(self.bot, gid, token),
            "snipe_block": lambda: dashboard_snipe.render_snipe_block(self.bot, gid, token),
            "tag_block": lambda: dashboard_tags.render_tags_block(self.bot, gid, token),
            "curhat_block": lambda: dashboard_curhat.render_curhat_block(self.bot, gid, token),
            "form_inbox_block": lambda: dashboard_form_inbox.render_inbox_block(self.bot, gid, token),
            "stats_block": lambda: dashboard_stats.render_stats_block(self.bot, gid, token),
            "bangun_block": lambda: dashboard_bangun.render_bangun_block(self.bot, gid, token),
            "gambar_block": lambda: dashboard_ai.render_gambar_block(self.bot, gid, token),
            "ai_prompt_block": lambda: dashboard_ai.render_prompt_server_block(gid, token),
            "ai_privasi_block": dashboard_ai.render_privasi_block,
            "info_block": lambda: dashboard_info.render_info_block(self.bot, gid, token),
            "voice_block": lambda: dashboard_voice.render_voice_block(self.bot, gid, token),
            "sosial_block": lambda: dashboard_sosial.render_sosial_block(self.bot, gid, token),
            "pantau_block": lambda: dashboard_highlights.render_highlights_block(self.bot, gid, token),
            "lencana_block": lambda: dashboard_lencana.render_lencana_block(self.bot, gid, token),
            "aturan_block": lambda: dashboard_ui.render_aturan_block(
                gid, token, dashboard_keamanan.collect(gid)
            ),
            "starboard_block": lambda: dashboard_ui.render_starboard_block(self.bot, gid, token),
            "giveaway_block": lambda: dashboard_ui.render_giveaway_block(
                gid, dashboard_giveaway.collect(gid), token, self.bot
            ),
        }
        return {nama: _blok(fn, '<div class="muted">Panel tidak tersedia.</div>')
                for nama, fn in peta.items()}

    def _blok_sambutan(self, slug: str, gid: int, setelan) -> dict:
        """Halaman sambutan: tiga bagian (welcome/goodbye/boost) di satu halaman."""
        kosong = {nama: "" for nama in (
            "setelan_welcome", "setelan_goodbye", "setelan_boost",
            "kartu_welcome", "kartu_goodbye", "kartu_boost",
            "uji_welcome", "uji_goodbye", "uji_boost", "kartu_block",
        )}
        if slug != "sambutan":
            return kosong
        hasil = {
            "setelan_welcome": setelan(SETELAN_SAMBUTAN),
            "setelan_goodbye": setelan(SETELAN_PERPISAHAN),
            "setelan_boost": setelan(SETELAN_BOOST),
        }
        for jenis in ("welcome", "goodbye", "boost"):
            hasil[f"kartu_{jenis}"] = _blok(
                lambda j=jenis: dashboard_ui.render_kartu_block(gid, "", hanya=(j,)),
                '<div class="muted">Kartu tidak tersedia.</div>',
            )
            hasil[f"uji_{jenis}"] = _blok(
                lambda j=jenis: dashboard_ui.render_uji_block(self.bot, gid, "", hanya=(j,)),
                '<div class="muted">Tes fitur tidak tersedia.</div>',
            )
        hasil["kartu_block"] = ""
        return hasil

    def _susun_blok(self, slug: str, gid: int, *, slug_halaman: str = "") -> dict:
        """Render semua blok panel, lalu pilih yang relevan untuk `slug`.

        Setiap blok dibungkus `_blok()`: satu panel yang gagal tidak mematikan
        seluruh halaman.
        """
        nilai = _nilai_setelan(gid)

        def setelan(kunci: tuple[str, ...]) -> str:
            return _blok(
                lambda: dashboard_ui.render_setelan_block(nilai, self.bot, gid, "", hanya=kunci),
                '<div class="muted">Setelan tidak tersedia.</div>',
            )

        def blok(fn, bawaan: str) -> str:
            return _blok(fn, bawaan)

        # --- panel yang selalu dirender ---
        semua = {
            "kontrol_block": blok(lambda: render_controls_block(gid, ""), ""),
            "fitur_block": blok(lambda: render_features_block(gid), ""),
            "kirim_block": blok(lambda: dashboard_ui.render_kirim_block(self.bot, gid, ""), ""),
            "buat_block": blok(lambda: dashboard_ui.render_buat_block(self.bot, gid, ""), ""),
            "konten_block": blok(
                lambda: dashboard_ui.render_konten_block(gid, dashboard_pesan.daftar_konten(gid, self.bot), ""),
                "",
            ),
            "tiket_block": blok(
                lambda: dashboard_ui.render_tiket_block(gid, dashboard_tiket.collect_tiket(gid), "", self.bot),
                "",
            ),
            "arsip_block": blok(
                lambda: dashboard_ui.render_arsip_block(
                    gid, "", ticket_archive.statistik(gid), ticket_archive.daftar(gid, limit=5)
                ),
                "",
            ),
            "panel_block": blok(
                lambda: dashboard_ui.render_panel_block(self.bot, gid, dashboard_panel.collect_panel(gid), ""),
                "",
            ),
        }
        # --- panel fitur opsional: nama atribut render_*/collect_* dipetakan di bawah ---
        semua.update(self._blok_opsional(gid))
        semua.update(self._blok_sambutan(slug, gid, setelan))
        semua["uji_block"] = blok(
            lambda: dashboard_ui.render_uji_block(self.bot, gid, "", hanya=UJI_HALAMAN.get(slug, ())),
            "",
        )
        grup_slug = {v: k for k, v in GRUP_HALAMAN.items()}.get(slug)
        semua["setelan_block"] = setelan(fitur_grup(grup_slug)) if grup_slug else ""
        semua["ekspor_block"] = blok(lambda: dashboard_ui.render_ekspor_block(gid, ""), "")
        semua["audit_block"] = blok(
            lambda: dashboard_ui.render_audit_block(dashboard_admin.audit_terakhir(gid, limit=8)), ""
        )
        semua["banner_block"] = blok(lambda: dashboard_ui.render_banner_block(gid, ""), "")
        semua["moderasi_block"] = blok(
            lambda: dashboard_moderasi.render_moderasi_block(self.bot, gid, ""), ""
        )
        semua["tren_block"] = ""
        return semua

