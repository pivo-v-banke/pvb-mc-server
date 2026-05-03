from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SpaceConf:
    server_host: str = "127.0.0.1"
    server_port: int = 25565
    # Адрес HTTP-хаба в URL для pack.lock.toml (как клиенты достучатся до /spaces/.../mods/).
    hub_public_host: str = "127.0.0.1"
    hub_public_port: int = 9090
    rcon_port: int = 25575
    rcon_password: str = "changeme"
    image: str = "itzg/minecraft-server:latest"
    # Human-readable label for hub / launcher (optional; defaults to space folder name in UI)
    space_display_name: str = ""

    @staticmethod
    def from_file(path: Path) -> SpaceConf:
        if not path.exists():
            return SpaceConf()

        raw: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if not value or value.startswith("#") or "=" not in value:
                continue
            k, v = value.split("=", 1)
            raw[k.strip()] = v.strip()

        hub_host = raw.get("HUB_PUBLIC_HOST") or raw.get("PACK_HOST", "127.0.0.1")
        if "HUB_PUBLIC_PORT" in raw:
            hub_port = int(raw["HUB_PUBLIC_PORT"])
        elif "PACK_HTTP_PORT" in raw:
            hub_port = int(raw["PACK_HTTP_PORT"])
        else:
            hub_port = 9090

        return SpaceConf(
            server_host=raw.get("SERVER_HOST", "127.0.0.1"),
            server_port=int(raw.get("SERVER_PORT", "25565")),
            hub_public_host=hub_host,
            hub_public_port=hub_port,
            rcon_port=int(raw.get("RCON_PORT", "25575")),
            rcon_password=raw.get("RCON_PASSWORD", "changeme"),
            image=raw.get("IMAGE", "itzg/minecraft-server:latest"),
            space_display_name=raw.get("SPACE_DISPLAY_NAME", "").strip(),
        )

    def to_template_text(self) -> str:
        return "\n".join(
            [
                "# Адрес игрового сервера для клиентов (лаунчер / список миров)",
                f"SERVER_HOST={self.server_host}",
                f"SERVER_PORT={self.server_port}",
                "# Host и порт HTTP-хаба так, как до него ходят клиенты (URL модов в pack.lock.toml)",
                f"HUB_PUBLIC_HOST={self.hub_public_host}",
                f"HUB_PUBLIC_PORT={self.hub_public_port}",
                f"RCON_PORT={self.rcon_port}",
                f"RCON_PASSWORD={self.rcon_password}",
                f"IMAGE={self.image}",
                f"SPACE_DISPLAY_NAME={self.space_display_name}",
                "",
            ]
        )
