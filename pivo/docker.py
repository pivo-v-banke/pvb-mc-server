from __future__ import annotations

import logging
import re
import subprocess

from pivo.conf import SpaceConf
from pivo.pack import PackInfo
from pivo.paths import SpacePaths

LOG = logging.getLogger(__name__)

def container_name(space_name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", space_name).strip("-")
    return f"pivo-{safe}"


def run_quiet(cmd: list[str]) -> None:
    LOG.debug("exec: %s", " ".join(cmd))
    subprocess.run(  # noqa: S603
        cmd,
        check=False,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run_checked(cmd: list[str]) -> None:
    LOG.debug("exec: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, text=True)  # noqa: S603


def start(space_name: str, space: SpacePaths, pack: PackInfo, conf: SpaceConf) -> None:
    name = container_name(space_name)
    space.data_dir.mkdir(parents=True, exist_ok=True)

    LOG.info("Starting docker container: %s", name)
    run_quiet(["docker", "rm", "-f", name])

    env = [
        "-e",
        "EULA=TRUE",
        "-e",
        f"VERSION={pack.minecraft_version}",
        "-e",
        "ENABLE_RCON=true",
        "-e",
        f"RCON_PASSWORD={conf.rcon_password}",
    ]
    if pack.loader == "fabric":
        env += ["-e", "TYPE=FABRIC"]
    elif pack.loader == "neoforge":
        env += ["-e", "TYPE=NEOFORGE"]
        if pack.loader_version and pack.loader_version not in {"latest"}:
            env += ["-e", f"NEOFORGE_VERSION={pack.loader_version}"]
    else:
        raise ValueError(f"Unsupported loader: {pack.loader}")

    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "-p",
        f"{conf.server_port}:25565",
        "-p",
        f"{conf.rcon_port}:25575",
        *env,
        "-v",
        f"{space.data_dir}:/data",
        conf.image,
    ]
    run_checked([str(x) for x in cmd])


def stop(space_name: str) -> None:
    LOG.info("Stopping docker container: %s", container_name(space_name))
    subprocess.run(["docker", "stop", container_name(space_name)], check=False, text=True)  # noqa: S603


def restart(space_name: str) -> None:
    LOG.info("Restarting docker container: %s", container_name(space_name))
    subprocess.run(["docker", "restart", container_name(space_name)], check=False, text=True)  # noqa: S603


def logs(space_name: str, *, follow: bool, tail: str) -> int:
    cmd = ["docker", "logs"]
    if follow:
        cmd.append("-f")
    cmd += ["--tail", tail, container_name(space_name)]
    return subprocess.call(cmd)  # noqa: S603


def rcon(space_name: str) -> int:
    cmd = ["docker", "exec", "-it", container_name(space_name), "rcon-cli"]
    return subprocess.call(cmd)  # noqa: S603

