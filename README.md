# pivo-v-mc-server

Server-side orchestrator for a Minecraft modpack with:
- lock-based mod manifest (`pack.toml`)
- automatic server mod sync
- Dockerized Minecraft server startup
- HTTP **hub** (`pivo-cli start-hub`): clients fetch lock + mods at `/spaces/<name>/...`

## Requirements

- Linux
- Docker
- Python 3.11+

## Quick Start

1. Edit `pack.toml`.
2. Start the stack:

```bash
./start-server -p 25565 -f ./pack.toml
```

This command:
- validates and syncs server-side mods to `runtime/mods`
- writes `runtime/public/pack.lock.toml` with mod URLs pointing at the **hub** (`HUB_HTTP_ORIGIN`, see script env vars)
- launches Minecraft server container on the selected game port

There is no separate “pack-only” HTTP listener anymore; distribution goes through the hub reading `spaces/<space>/public/` on disk.

## Pack Format

Use this schema in `pack.toml`:

```toml
[pack]
name = "Pivo v MC"
minecraft_version = "1.20.1"
loader = "fabric"
loader_version = "0.15.11"

[[mods]]
id = "sodium"
filename = "sodium-fabric-0.5.8.jar"
sha256 = "<sha256>"
source_url = "https://cdn.example/mods/sodium-fabric-0.5.8.jar"
side = "client"

[[mods]]
id = "lithium"
filename = "lithium-fabric-mc1.20.1-0.11.2.jar"
sha256 = "<sha256>"
source_url = "https://cdn.example/mods/lithium-fabric-mc1.20.1-0.11.2.jar"
side = "both"
```

Allowed values for `side`: `client`, `server`, `both`.
