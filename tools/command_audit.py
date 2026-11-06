"""Laporan permukaan command: berapa yang terlihat member vs khusus pengelola.

Pakai:  python tools/command_audit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import command_policy  # noqa: E402
import main  # noqa: E402


def main_cli() -> int:
    tree = main.bot.tree
    sebelum = command_policy.audit(tree)
    diterapkan = command_policy.apply(tree)
    sesudah = command_policy.audit(tree)

    print("Permukaan command AI Discord Chat")
    print("-" * 46)
    print(f"Command utama          : {sesudah['top_level']}")
    print(f"Subcommand             : {sesudah['subcommand']}")
    print(f"Total entri            : {sesudah['total']}  (sebelum: {sebelum['total']})")
    print(f"Khusus pengelola       : {diterapkan['entri_tersembunyi']} entri disembunyikan")
    print(f"  · Administrator      : {diterapkan['admin']} command")
    print(f"  · Manage Server      : {diterapkan['manage']} command")
    print(f"  · Moderasi           : {diterapkan['mod']} command")
    print(f"Terlihat member biasa  : {sesudah['terlihat_member']}")
    print()
    print("Command yang tetap terlihat semua orang:")
    nama = [
        c.name
        for c in sorted(tree.get_commands(), key=lambda c: c.name)
        if getattr(c, "default_member_permissions", None) is None
        and not c.name.startswith(("🌐", "💡", "🔍"))
    ]
    print("  " + ", ".join(nama))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
