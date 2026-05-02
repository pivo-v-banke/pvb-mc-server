#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import shutil
import tomllib
from pathlib import Path
from urllib.request import urlopen

ALLOWED_SIDES = {"client", "server", "both"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-file", required=True)
    parser.add_argument("--mods-dir", required=False)
    parser.add_argument("--public-dir", required=False)
    parser.add_argument("--server-host", required=False, default="127.0.0.1")
    parser.add_argument("--server-port", required=False, type=int, default=8080)
    parser.add_argument("--print-minecraft-version", action="store_true")
    parser.add_argument("--print-loader", action="store_true")
    parser.add_argument("--print-loader-version", action="store_true")
    return parser.parse_args()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def download_mod(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=120) as response:
        target.write_bytes(response.read())


def validate_manifest(pack_data: dict) -> None:
    if "pack" not in pack_data:
        raise ValueError("Missing [pack] section in pack.toml")

    if "mods" not in pack_data:
        raise ValueError("Missing [[mods]] entries in pack.toml")

    for mod in pack_data["mods"]:
        for key in ("id", "filename", "sha256", "source_url", "side"):
            if key not in mod:
                raise ValueError(f"Mod entry is missing `{key}` field")
        if mod["side"] not in ALLOWED_SIDES:
            raise ValueError(f"Invalid side `{mod['side']}` for mod `{mod['id']}`")


def build_public_lock(
    pack_data: dict,
    mods: list[dict],
    server_host: str,
    server_port: int,
) -> str:
    lines: list[str] = []
    pack = pack_data["pack"]
    lines.append("[pack]")
    lines.append(f'name = "{pack["name"]}"')
    lines.append(f'minecraft_version = "{pack["minecraft_version"]}"')
    lines.append(f'loader = "{pack["loader"]}"')
    lines.append(f'loader_version = "{pack["loader_version"]}"')
    lines.append("")
    lines.append("[distribution]")
    lines.append(f'server_host = "{server_host}"')
    lines.append(f"server_port = {server_port}")
    lines.append("")

    for mod in mods:
        lines.append("[[mods]]")
        lines.append(f'id = "{mod["id"]}"')
        lines.append(f'filename = "{mod["filename"]}"')
        lines.append(f'sha256 = "{mod["sha256"]}"')
        lines.append(f'side = "{mod["side"]}"')
        lines.append(f'url = "http://{server_host}:{server_port}/mods/{mod["filename"]}"')
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def run() -> int:
    args = parse_args()
    pack_file = Path(args.pack_file).resolve()
    pack_data = tomllib.loads(pack_file.read_text(encoding="utf-8"))
    validate_manifest(pack_data)

    if args.print_minecraft_version:
        print(pack_data["pack"]["minecraft_version"])
        return 0

    if args.print_loader:
        print(pack_data["pack"]["loader"])
        return 0

    if args.print_loader_version:
        print(pack_data["pack"]["loader_version"])
        return 0

    if not args.mods_dir or not args.public_dir:
        raise ValueError("`--mods-dir` and `--public-dir` are required for sync mode")

    mods_dir = Path(args.mods_dir).resolve()
    public_dir = Path(args.public_dir).resolve()
    public_mods_dir = public_dir / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    public_mods_dir.mkdir(parents=True, exist_ok=True)
    mods_root = mods_dir.resolve()
    public_mods_root = public_mods_dir.resolve()

    server_mods = []
    public_mods = []
    for mod in pack_data["mods"]:
        filename = str(mod["filename"])
        local_mod_path = (mods_root / filename).resolve()
        if mods_root not in local_mod_path.parents and local_mod_path != mods_root:
            # Prevent path traversal / absolute paths; fall back to basename
            filename = Path(filename).name
            local_mod_path = (mods_root / filename).resolve()
        if not local_mod_path.exists():
            download_mod(mod["source_url"], local_mod_path)

        current_sha = sha256_of(local_mod_path)
        if current_sha != mod["sha256"]:
            local_mod_path.unlink(missing_ok=True)
            download_mod(mod["source_url"], local_mod_path)
            current_sha = sha256_of(local_mod_path)
            if current_sha != mod["sha256"]:
                raise ValueError(f"SHA256 mismatch for mod `{mod['id']}`")

        public_mod_path = (public_mods_root / filename).resolve()
        if public_mods_root not in public_mod_path.parents and public_mod_path != public_mods_root:
            filename = Path(filename).name
            public_mod_path = (public_mods_root / filename).resolve()
        public_mod_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_mod_path, public_mod_path)
        public_mods.append(
            {
                "id": mod["id"],
                "filename": filename,
                "sha256": mod["sha256"],
                "side": mod["side"],
            }
        )
        if mod["side"] in {"server", "both"}:
            server_mods.append(filename)

    # Keep only server-relevant jars in runtime/mods for Docker mount.
    for file in mods_dir.rglob("*.jar"):
        rel = file.relative_to(mods_dir).as_posix()
        if rel not in server_mods and file.name not in server_mods:
            file.unlink(missing_ok=True)

    lock_text = build_public_lock(pack_data, public_mods, args.server_host, args.server_port)
    (public_dir / "pack.lock.toml").write_text(lock_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
