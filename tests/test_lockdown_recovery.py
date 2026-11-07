"""Pemulihan lockdown: izin awal, state lintas restart, & perubahan manual."""

from __future__ import annotations

import json
import types

import pytest

import server_tools as st


class _HTTPFailure(st.discord.HTTPException):
    def __init__(self):
        Exception.__init__(self, "simulated permission failure")


class _Channel:
    def __init__(self, channel_id: int, send_messages: bool | None):
        self.id = channel_id
        self.send_messages = send_messages
        self.calls = []
        self.fail_restore = False

    def overwrites_for(self, _role):
        return types.SimpleNamespace(send_messages=self.send_messages)

    async def set_permissions(self, _role, *, send_messages, reason):
        self.calls.append({"send_messages": send_messages, "reason": reason})
        if self.fail_restore and send_messages is not False:
            raise _HTTPFailure()
        self.send_messages = send_messages


class _Guild:
    def __init__(self, *channels):
        self.id = 314159
        self.default_role = object()
        self.text_channels = list(channels)
        self.channels = {channel.id: channel for channel in channels}

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    async def fetch_channel(self, channel_id):
        return self.channels[channel_id]


@pytest.fixture(autouse=True)
def _isolated_lockdown_file(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "LOCKDOWN_FILE", tmp_path / "data" / "lockdown.json")
    monkeypatch.setattr(st, "AFK_FILE", tmp_path / "data" / "afk.json")
    st.lockdown_state.clear()
    yield
    st.lockdown_state.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("original", [None, True])
async def test_lockdown_persists_and_restores_exact_original_permission(original):
    channel = _Channel(1001, original)
    guild = _Guild(channel)

    locked, failed = await st.start_lockdown(guild, by_id=7, reason="uji")
    assert (locked, failed) == (1, 0)
    assert channel.send_messages is False
    assert st.LOCKDOWN_FILE.exists()
    saved = json.loads(st.LOCKDOWN_FILE.read_text("utf-8"))[str(guild.id)]
    assert saved["channels"] == [{"id": channel.id, "send_messages": original}]

    # Simulasikan proses bot yang restart: hanya state di disk yang tertinggal.
    st.lockdown_state.clear()
    assert st.load_server_tools_from_disk() == (0, 0)
    assert st.lockdown_active(guild.id)["recovered"] is True

    assert await st.stop_lockdown(guild) == 1
    assert channel.send_messages is original
    assert st.lockdown_active(guild.id) is None
    assert not st.LOCKDOWN_FILE.exists()


@pytest.mark.asyncio
async def test_lockdown_tidak_mengubah_atau_mencatat_channel_yang_sudah_denied():
    channel = _Channel(1002, False)
    guild = _Guild(channel)

    assert await st.start_lockdown(guild, by_id=7) == (0, 0)
    assert channel.calls == []
    assert st.lockdown_active(guild.id) is None


@pytest.mark.asyncio
async def test_pemulihan_mempertahankan_izin_yang_diubah_manual():
    channel = _Channel(1003, None)
    guild = _Guild(channel)
    assert await st.start_lockdown(guild, by_id=7) == (1, 0)

    # Admin lain membuka izin secara manual selagi lockdown berlangsung.
    channel.send_messages = True
    assert await st.stop_lockdown(guild) == 0
    assert channel.send_messages is True
    assert len(channel.calls) == 1  # stop tidak menimpa perubahan manual
    assert st.lockdown_active(guild.id) is None


@pytest.mark.asyncio
async def test_gagal_memulihkan_tetap_tersimpan_untuk_dicoba_lagi():
    channel = _Channel(1004, True)
    guild = _Guild(channel)
    assert await st.start_lockdown(guild, by_id=7) == (1, 0)

    channel.fail_restore = True
    assert await st.stop_lockdown(guild) == 0
    assert st.lockdown_active(guild.id) is not None
    assert st.LOCKDOWN_FILE.exists()

    channel.fail_restore = False
    assert await st.stop_lockdown(guild) == 1
    assert channel.send_messages is True
    assert st.lockdown_active(guild.id) is None
