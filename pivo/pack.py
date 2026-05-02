from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tomlkit import dump, parse
from tomlkit.items import Array, Table


@dataclass(frozen=True)
class PackInfo:
    minecraft_version: str
    loader: str
    loader_version: str


def read_pack(path: Path) -> Table:
    if not path.exists():
        raise FileNotFoundError(f"Pack file not found: {path}")
    return parse(path.read_text(encoding="utf-8"))


def write_pack(path: Path, doc: Table) -> None:
    with path.open("w", encoding="utf-8") as f:
        dump(doc, f)


def ensure_mods_array(doc: Table) -> Array:
    if "mods" not in doc:
        doc["mods"] = []
    mods = doc["mods"]
    if not isinstance(mods, list):
        raise ValueError("Expected `mods` to be an array of tables")
    return mods


def get_pack_info(doc: Table) -> PackInfo:
    pack = doc.get("pack")
    if not isinstance(pack, dict):
        raise ValueError("Invalid pack.toml: missing [pack]")

    mc = str(pack.get("minecraft_version", "")).strip()
    loader = str(pack.get("loader", "")).strip()
    loader_version = str(pack.get("loader_version", "")).strip()
    if not mc or not loader:
        raise ValueError("Invalid pack.toml: [pack] requires minecraft_version and loader")
    return PackInfo(minecraft_version=mc, loader=loader, loader_version=loader_version)

