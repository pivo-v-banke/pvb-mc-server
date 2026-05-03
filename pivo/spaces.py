from __future__ import annotations

import shutil
from pathlib import Path

from pivo.conf import SpaceConf
from pivo.paths import RepoPaths, SpacePaths

# Used when create-space --from-pack runs but repo root pack.toml is missing:
# real metadata comes from the mrpack import immediately after.
_PLACEHOLDER_PACK_TOML = """[pack]
name = "placeholder"
minecraft_version = "1.21.1"
loader = "fabric"
loader_version = "0.16.0"
mods = []
"""


def ensure_repo_layout(repo: RepoPaths) -> None:
    repo.spaces_dir.mkdir(parents=True, exist_ok=True)


def space_root(repo: RepoPaths, name: str) -> Path:
    return (repo.spaces_dir / name).resolve()


def require_space(repo: RepoPaths, name: str | None) -> SpacePaths:
    if not name:
        raise ValueError("Space is required. Use -s <space_name>.")
    root = space_root(repo, name)
    if not root.exists():
        raise FileNotFoundError(f"Space not found: {name} ({root})")
    return SpacePaths(root=root)


def create_space(repo: RepoPaths, name: str, *, template_pack: Path | None) -> SpacePaths:
    root = space_root(repo, name)
    if root.exists():
        raise FileExistsError(f"Space already exists: {name} ({root})")
    space = SpacePaths(root=root)
    space.data_dir.mkdir(parents=True, exist_ok=True)
    space.public_dir.mkdir(parents=True, exist_ok=True)

    if template_pack is None:
        space.pack_toml.write_text(_PLACEHOLDER_PACK_TOML, encoding="utf-8")
    else:
        if not template_pack.exists():
            raise FileNotFoundError(f"Template pack not found: {template_pack}")
        shutil.copy2(template_pack, space.pack_toml)

    if not space.conf.exists():
        space.conf.write_text(SpaceConf().to_template_text(), encoding="utf-8")

    if not space.jvm_args.exists():
        space.jvm_args.write_text(
            "\n".join(
                [
                    "# Куча: pivo-cli передаёт -Xms/-Xmx в контейнер как INIT_MEMORY / MAX_MEMORY",
                    "# (образ itzg перезаписывает data/user_jvm_args.txt при старте — см. jvm_itzg).",
                    "# Прочие флаги Java — в тех же строках; уйдут в JVM_OPTS.",
                    "-Xms2G",
                    "-Xmx4G",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    if not space.description_md.exists():
        space.description_md.write_text("", encoding="utf-8")

    return space

