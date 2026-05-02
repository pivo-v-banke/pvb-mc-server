from __future__ import annotations

import logging
import subprocess
import sys

from pivo.conf import SpaceConf
from pivo.paths import RepoPaths, SpacePaths

LOG = logging.getLogger(__name__)

def sync_mods(repo: RepoPaths, space: SpacePaths, conf: SpaceConf) -> None:
    space.data_dir.mkdir(parents=True, exist_ok=True)
    space.public_dir.mkdir(parents=True, exist_ok=True)
    mods_dir = space.data_dir / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(repo.sync_mods_script),
        "--pack-file",
        str(space.pack_toml),
        "--mods-dir",
        str(mods_dir),
        "--public-dir",
        str(space.public_dir),
        "--server-host",
        conf.pack_host,
        "--server-port",
        str(conf.pack_http_port),
    ]
    LOG.info("Syncing mods (pack=%s)", space.pack_toml)
    subprocess.run(cmd, check=True, text=True)  # noqa: S603


def apply_jvm_args(space: SpacePaths) -> None:
    # itzg/minecraft-server reads JVM args from /data/user_jvm_args.txt
    if not space.jvm_args.exists():
        LOG.debug("No jvm.args found in %s", space.root)
        return
    space.data_dir.mkdir(parents=True, exist_ok=True)
    LOG.info("Applying jvm.args")
    space.data_user_jvm_args.write_text(space.jvm_args.read_text(encoding="utf-8"), encoding="utf-8")

