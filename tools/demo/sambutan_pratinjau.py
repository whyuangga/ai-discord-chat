"""Pratinjau dashboard untuk fitur **empat tampilan sambutan** (mode demo).

Menjalankan dashboard sungguhan dengan data contoh supaya halaman
`/sambutan` bisa dilihat langsung di browser tanpa bot Discord.

Jalankan:
    DASHBOARD_TOKEN=... DASHBOARD_PORT=8080 python3 tools/demo/sambutan_pratinjau.py
lalu buka http://127.0.0.1:8080/sambutan?token=demo&guild=1
"""

import asyncio
from types import SimpleNamespace

import community_agent
import web_dashboard

GID = 1


class _Role:
    def __init__(self, rid, nama, bawaan=False):
        self.id = rid
        self.name = nama
        self._bawaan = bawaan

    def is_default(self):
        return self._bawaan


class _Channel:
    def __init__(self, cid, nama):
        self.id = cid
        self.name = nama
        self.mention = f"#{nama}"


class _Guild:
    id = GID
    name = "Whyu Test"
    member_count = 3
    roles = [_Role(1, "@everyone", True), _Role(9, "Admin")]
    categories = []
    text_channels = [_Channel(600, "welcome"), _Channel(601, "perpisahan")]

    def get_channel(self, cid):
        return next((c for c in self.text_channels if c.id == cid), None)


guild = _Guild()


class _Bot:
    user = SimpleNamespace(name="DemoBot", display_name="DemoBot")

    def get_guild(self, gid):
        return guild if int(gid) == GID else None

    def get_channel(self, cid):
        return guild.get_channel(int(cid))

    def get_user(self, uid):  # pragma: no cover - demo saja
        return None


def siapkan_data():
    """Isi setelan contoh: sambutan mode Container, perpisahan mode Embed."""
    community_agent.welcome_agent_guilds[GID] = community_agent.set_welcome_config(
        GID, 600, enabled=True
    )
    community_agent.set_welcome_card_mode(GID, "container")
    community_agent.set_template_greeting(
        GID, "welcome", "Selamat datang **{user_mention}** di **{server}**!\nKamu member ke-{member_count} 🎉"
    )
    community_agent.goodbye_agent_guilds[GID] = {
        "enabled": True,
        "channel_id": 601,
        "view_mode": "embed",
        "template": "Sampai jumpa, **{user_name}** 👋",
    }
    community_agent.boost_agent_guilds[GID] = {"enabled": True, "channel_id": 600}


async def main():
    siapkan_data()
    bot = _Bot()
    jalan = await web_dashboard.start_dashboard(bot)
    cfg = web_dashboard.dashboard_config()
    print(f"dashboard aktif: {jalan} | port {cfg['port']} | token {cfg['token']}")
    print(f"buka: http://127.0.0.1:{cfg['port']}/sambutan?token={cfg['token']}&guild={GID}")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
