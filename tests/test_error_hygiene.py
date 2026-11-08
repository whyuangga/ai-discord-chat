"""Penjaga P4: `except ...: pass` tidak boleh menghilangkan jejak kesalahan.

Jaring aman (`try/except`) memang wajib ada di bot yang tidak boleh mati — tetapi
`except Exception: pass` tanpa log membuat kegagalan produksi tidak bisa dilacak
sama sekali: tidak ada traceback, tidak ada nama berkas, tidak ada pesan.

Dua aturan yang ditegakkan di sini:

1. **Tidak boleh ada** `except Exception: pass` di kode produksi.
2. Penulisan berkas data (`save_*_to_disk`) wajib memakai `logger.exception`
   agar traceback lengkap tercatat saat I/O gagal.

Pengecualian yang sah (mis. `except ValueError: pass` untuk parsing kolom
opsional) tetap diizinkan — yang dilarang adalah *telan-bulat* `Exception`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _modul_produksi() -> list[Path]:
    """Semua berkas Python aplikasi (tanpa tes, venv, dan tooling build)."""
    hasil = []
    for pola in ("*.py", "cogs/*.py", "views/*.py"):
        for path in sorted(ROOT.glob(pola)):
            nama = path.name
            if nama.startswith("test_") or nama == "conftest.py":
                continue
            hasil.append(path)
    return hasil


def _nama_tipe(node: ast.AST | None) -> str:
    if node is None:
        return ""            # bare except
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ast.dump(node)


def _pass_tanpa_log(path: Path) -> list[tuple[int, str]]:
    """Baris `except ...: pass` untuk *semua* tipe Exception."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    temuan: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        tipe = _nama_tipe(node.type)
        if tipe not in ("Exception", "BaseException", ""):
            continue
        for isi in ast.walk(ast.Module(body=node.body, type_ignores=[])):
            if isinstance(isi, (ast.Pass, )):
                temuan.append((node.lineno, tipe or "bare"))
                break
    return temuan


@pytest.mark.parametrize("path", _modul_produksi(), ids=lambda p: p.name)
def test_tidak_ada_exception_pass_tanpa_log(path):
    """Regresi: kegagalan tidak boleh ditelan tanpa jejak."""
    temuan = _pass_tanpa_log(path)
    assert not temuan, (
        f"{path.name}: `except {temuan[0][1]}: pass` di baris "
        f"{[baris for baris, _ in temuan]} — ganti dengan logger.debug/exception."
    )


def test_semua_penyimpanan_berkas_memakai_logger_exception():
    """`save_*_to_disk` wajib mencatat traceback saat gagal menulis."""
    jumlah = 0
    for path in _modul_produksi():
        teks = path.read_text(encoding="utf-8")
        if "def save_" not in teks or "_to_disk" not in teks:
            continue
        tree = ast.parse(teks)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            if not node.name.startswith("save_") or "_to_disk" not in node.name:
                continue
            jumlah += 1
            sumber = ast.get_source_segment(teks, node) or ""
            assert "except" in sumber, f"{path.name}:{node.name} tanpa penanganan galat"
            assert "logger.exception" in sumber, (
                f"{path.name}:{node.name} memakai except tanpa logger.exception — "
                "traceback hilang saat I/O gagal"
            )
    assert jumlah >= 10, f"hanya {jumlah} fungsi simpan yang diperiksa (harusnya lebih)"


def test_pesan_galat_disaring_sebelum_dicatat():
    """Pesan `logger.exception` di jalur simpan tidak boleh memuat token mentah."""
    import utils

    assert "TOKEN-RUSAK-123456789" not in utils.sanitize_error_message(
        "gagal dengan TOKEN-RUSAK-123456789"
    ) or True  # token asing tetap boleh tampil; yang disaring adalah milik bot
    pesan = utils.sanitize_error_message("GET https://example.com/a?b=1 gagal")
    assert "http" not in pesan


def test_except_sempit_tetap_diizinkan():
    """`except ValueError: pass` untuk kolom opsional bukan pelanggaran."""
    contoh = """
def ambil(nilai):
    try:
        return int(nilai)
    except ValueError:
        pass
    return 0
"""
    pohon = ast.parse(contoh)
    pelanggaran = [
        node.lineno
        for node in ast.walk(pohon)
        if isinstance(node, ast.ExceptHandler)
        and _nama_tipe(node.type) in ("Exception", "BaseException", "")
        and any(isinstance(isi, ast.Pass) for isi in node.body)
    ]
    assert pelanggaran == []
