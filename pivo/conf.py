from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SpaceConf:
    server_host: str = "127.0.0.1"
    server_port: int = 25565
    pack_http_port: int = 8080
    pack_host: str = "127.0.0.1"
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

        return SpaceConf(
            server_host=raw.get("SERVER_HOST", "127.0.0.1"),
            server_port=int(raw.get("SERVER_PORT", "25565")),
            pack_http_port=int(raw.get("PACK_HTTP_PORT", "8080")),
            pack_host=raw.get("PACK_HOST", "127.0.0.1"),
            rcon_port=int(raw.get("RCON_PORT", "25575")),
            rcon_password=raw.get("RCON_PASSWORD", "changeme"),
            image=raw.get("IMAGE", "itzg/minecraft-server:latest"),
            space_display_name=raw.get("SPACE_DISPLAY_NAME", "").strip(),
        )

    def to_template_text(self) -> str:
        return "\n".join(
            [
                f"SERVER_HOST={self.server_host}",
                f"SERVER_PORT={self.server_port}",
                f"PACK_HTTP_PORT={self.pack_http_port}",
                f"PACK_HOST={self.pack_host}",
                f"RCON_PORT={self.rcon_port}",
                f"RCON_PASSWORD={self.rcon_password}",
                f"IMAGE={self.image}",
                f"SPACE_DISPLAY_NAME={self.space_display_name}",
                "",
            ]
        )
