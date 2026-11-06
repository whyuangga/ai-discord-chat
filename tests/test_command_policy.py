"""Uji kebijakan visibilitas command (`command_policy.py`)."""

from __future__ import annotations

import command_policy as cp


class FakeCommand:
    def __init__(self, name, subs=0):
        self.name = name
        self.commands = [FakeCommand(f"{name}-{i}") for i in range(subs)]
        self.default_member_permissions = None


class FakeTree:
    def __init__(self, commands):
        self._commands = commands

    def get_commands(self):
        return list(self._commands)


def test_policy_memetakan_izin():
    assert cp.policy_for("menu").administrator is True
    assert cp.policy_for("prefix").manage_guild is True
    assert cp.policy_for("mod").moderate_members is True
    assert cp.policy_for("level") is None
    assert cp.policy_for("TIDAK-ADA") is None


def test_apply_menyembunyikan_command_pengelola():
    tree = FakeTree([FakeCommand("menu", 3), FakeCommand("level", 2), FakeCommand("prefix", 1)])
    hasil = cp.apply(tree)

    assert tree.get_commands()[0].default_member_permissions.administrator is True
    assert tree.get_commands()[1].default_member_permissions is None   # tetap publik
    assert tree.get_commands()[2].default_member_permissions.manage_guild is True
    assert hasil == {"admin": 1, "manage": 1, "mod": 0, "entri_tersembunyi": 6}


def test_audit_menghitung_sebelum_dan_sesudah():
    tree = FakeTree([FakeCommand("menu", 3), FakeCommand("level", 2)])

    sebelum = cp.audit(tree)
    assert sebelum["total"] == 7 and sebelum["terlihat_member"] == 7

    cp.apply(tree)
    sesudah = cp.audit(tree)
    assert sesudah["tersembunyi"] == 4
    assert sesudah["terlihat_member"] == 3


def test_tree_asli_bot_terbaca_dan_berkurang():
    import main

    sebelum = cp.audit(main.bot.tree)
    cp.apply(main.bot.tree)
    sesudah = cp.audit(main.bot.tree)

    assert sesudah["total"] == sebelum["total"] > 200
    assert 0 < sesudah["tersembunyi"] < sesudah["total"]
    assert sesudah["terlihat_member"] < sebelum["total"]
