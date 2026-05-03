from __future__ import annotations

import logging
import subprocess
import sys

from pivo.conf import SpaceConf
from pivo.jvm_itzg import jvm_args_to_itzg_env
from pivo.paths import RepoPaths, SpacePaths

LOG = logging.getLogger(__name__)

def sync_mods(repo: RepoPaths, space: SpacePaths, conf: SpaceConf) -> None:
    space.data_dir.mkdir(parents=True, exist_ok=True)
    space.public_dir.mkdir(parents=True, exist_ok=True)
    mods_dir = space.data_dir / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)

    hub_origin = f"http://{conf.hub_public_host}:{conf.hub_public_port}"
    cmd = [
        sys.executable,
        str(repo.sync_mods_script),
        "--pack-file",
        str(space.pack_toml),
        "--mods-dir",
        str(mods_dir),
        "--public-dir",
        str(space.public_dir),
        "--minecraft-host",
        conf.server_host,
        "--minecraft-port",
        str(conf.server_port),
        "--hub-http-origin",
        hub_origin,
        "--space-name",
        space.root.name,
    ]
    LOG.info("Syncing mods (pack=%s)", space.pack_toml)
    subprocess.run(cmd, check=True, text=True)  # noqa: S603


def apply_jvm_args(space: SpacePaths) -> None:
    # itzg/minecraft-server перезаписывает /data/user_jvm_args.txt из MEMORY /
    # INIT_MEMORY / MAX_MEMORY при старте — кучу задаём через docker -e в
    # docker.start; здесь только чистим устаревшее и логируем маппинг.
    if not space.jvm_args.exists():
        LOG.debug("No jvm.args found in %s", space.root)
        return
    space.data_dir.mkdir(parents=True, exist_ok=True)
    mapped = jvm_args_to_itzg_env(space.jvm_args)
    LOG.info(
        "Applying jvm.args → itzg env on next start/reload: %s",
        mapped if mapped else "(heap не задан в jvm.args — образ возьмёт MEMORY по умолчанию, обычно 1G)",
    )
    space.data_user_jvm_args.write_text("", encoding="utf-8")

