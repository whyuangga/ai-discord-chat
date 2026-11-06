#!/usr/bin/env python3
"""Alat bantu dashboard untuk **pengguna yang menjalankan bot sendiri**.

Membuat token acak yang aman, bisa langsung ditulis ke `.env`, lalu menampilkan
alamat dashboard yang perlu dibuka. Tanpa dependency baru (stdlib saja).

Contoh pemakaian:

    python tools/dashboard_token.py                 # tampilkan token baru
    python tools/dashboard_token.py --tulis         # simpan ke .env (buat bila belum ada)
    python tools/dashboard_token.py --periksa       # cek .env sudah siap atau belum
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
CONTOH = AKAR / ".env.example"


def buat_token() -> str:
    """Token 43 karakter: hanya huruf, angka, `_` dan `-` (aman di URL & .env)."""
    return secrets.token_urlsafe(32)


def periksa_token(nilai: str) -> tuple[bool, str]:
    """Validasi token yang akan dipakai di `.env`."""
    teks = str(nilai or "")
    if len(teks) < 24:
        return False, "Token terlalu pendek — minimal 24 karakter."
    if re.search(r"[\s#'\"]", teks):
        return False, "Token tidak boleh berisi spasi, tanda kutip, atau `#`."
    return True, ""


def baca_env(path: Path) -> dict[str, str]:
    hasil: dict[str, str] = {}
    if not Path(path).exists():
        return hasil
    for baris in Path(path).read_text(encoding="utf-8").splitlines():
        bersih = baris.strip()
        if not bersih or bersih.startswith("#") or "=" not in bersih:
            continue
        kunci, _, nilai = bersih.partition("=")
        hasil[kunci.strip()] = nilai.strip()
    return hasil


def tulis_env(path: Path, kunci: str, nilai: str) -> bool:
    """Tulis/ganti satu kunci di `.env`. True bila berkas berubah."""
    target = Path(path)
    baris_baru = f"{kunci}={nilai}"
    if not target.exists():
        target.write_text(baris_baru + "\n", encoding="utf-8")
        return True
    isi = target.read_text(encoding="utf-8").splitlines()
    diganti = False
    for index, baris in enumerate(isi):
        if re.match(rf"^\s*{re.escape(kunci)}\s*=", baris):
            isi[index] = baris_baru
            diganti = True
            break
    if not diganti:
        isi.append(baris_baru)
    target.write_text("\n".join(isi).rstrip() + "\n", encoding="utf-8")
    return True


def status(env: dict[str, str]) -> list[str]:
    """Ringkas kesiapan dashboard berdasarkan isi `.env`."""
    catatan: list[str] = []
    token = env.get("DASHBOARD_TOKEN", "")
    port = env.get("DASHBOARD_PORT", "0")
    host = env.get("DASHBOARD_HOST", "0.0.0.0")
    refresh = env.get("DASHBOARD_REFRESH_SEC", "30")

    if not token:
        catatan.append("❌ DASHBOARD_TOKEN kosong → dashboard tidak menyala.")
    else:
        ok, galat = periksa_token(token)
        catatan.append("✅ DASHBOARD_TOKEN terisi." if ok else f"⚠️ {galat}")

    if str(port).strip() in ("", "0"):
        catatan.append(
            "ℹ️ DASHBOARD_PORT=0 → port diambil dari SERVER_PORT/PORT panel hosting. "
            "Di VPS/Termux isi angka, mis. 8080."
        )
    else:
        catatan.append(f"✅ DASHBOARD_PORT={port}")

    if str(host).strip() in ("0.0.0.0", ""):
        catatan.append(
            "ℹ️ DASHBOARD_HOST=0.0.0.0 → bisa diakses dari jaringan. "
            "Untuk akses lokal saja, pakai 127.0.0.1 + tunnel SSH."
        )
    catatan.append(
        "ℹ️ Auto-refresh "
        + ("mati (nyaman mengisi form)." if str(refresh).strip() == "0"
           else f"{refresh} detik — isi 0 bila form sering ter-reset.")
    )
    return catatan


def alamat(env: dict[str, str]) -> str:
    port = str(env.get("DASHBOARD_PORT", "0")).strip() or "0"
    if port == "0":
        port = "<port-panel>"
    token = env.get("DASHBOARD_TOKEN") or "<token>"
    return f"http://<ip-atau-domain>:{port}/?token={token}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Buat & pasang token dashboard untuk bot yang kamu jalankan sendiri."
    )
    parser.add_argument("--tulis", action="store_true", help="simpan token ke .env")
    parser.add_argument("--periksa", action="store_true", help="periksa kesiapan .env")
    parser.add_argument("--env", default=str(AKAR / ".env"), help="lokasi berkas .env")
    args = parser.parse_args(argv)

    path = Path(args.env)
    env = baca_env(path)

    if args.periksa:
        print(f"📄 Berkas: {path}")
        for baris in status(env):
            print("  " + baris)
        print("\n🔗 Buka dashboard di:")
        print("  " + alamat(env))
        return 0 if env.get("DASHBOARD_TOKEN") else 1

    token = env.get("DASHBOARD_TOKEN") or ""
    ok, _galat = periksa_token(token) if token else (False, "")
    if not ok:
        token = buat_token()
        if args.tulis:
            tulis_env(path, "DASHBOARD_TOKEN", token)
            if "DASHBOARD_PORT" not in env:
                tulis_env(path, "DASHBOARD_PORT", "8080")
            print(f"✅ Token ditulis ke {path}")
        else:
            print("🔑 Token baru (salin ke .env sebagai DASHBOARD_TOKEN):\n")
            print("  " + token + "\n")
    else:
        print("ℹ️ .env sudah punya token yang valid — tidak ada yang diubah.\n")

    env = baca_env(path)
    env.setdefault("DASHBOARD_TOKEN", token)
    print("📋 Ringkasan:")
    for baris in status(env):
        print("  " + baris)
    print("\n🔗 Alamat yang dibuka:")
    print("  " + alamat(env))
    if CONTOH.exists():
        print(f"\n💡 Semua variabel dijelaskan di {CONTOH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
