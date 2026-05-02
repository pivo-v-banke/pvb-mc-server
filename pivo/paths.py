from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepoPaths:
    root: Path

    @property
    def spaces_dir(self) -> Path:
        return self.root / "spaces"

    @property
    def scripts_dir(self) -> Path:
        return self.root / "scripts"

    @property
    def sync_mods_script(self) -> Path:
        return self.scripts_dir / "sync_mods.py"

    @property
    def serve_pack_script(self) -> Path:
        return self.scripts_dir / "serve_pack.py"

    @property
    def template_pack(self) -> Path:
        return self.root / "pack.toml"


@dataclass(frozen=True)
class SpacePaths:
    root: Path

    @property
    def pack_toml(self) -> Path:
        return self.root / "pack.toml"

    @property
    def jvm_args(self) -> Path:
        return self.root / "jvm.args"

    @property
    def conf(self) -> Path:
        return self.root / "pivo.conf"

    @property
    def description_md(self) -> Path:
        return self.root / "description.md"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def data_user_jvm_args(self) -> Path:
        return self.data_dir / "user_jvm_args.txt"

    @property
    def public_dir(self) -> Path:
        return self.root / "public"

    @property
    def backups_dir(self) -> Path:
        return self.root / "backups"

    @property
    def http_pid(self) -> Path:
        return self.root / "pack-http.pid"

    @property
    def http_log(self) -> Path:
        return self.root / "pack-http.log"
