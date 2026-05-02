from __future__ import annotations

import logging
import os
import subprocess
import sys

from pivo.paths import RepoPaths, SpacePaths

LOG = logging.getLogger(__name__)

def stop_http_server(space: SpacePaths) -> None:
    if not space.http_pid.exists():
        return
    try:
        pid = int(space.http_pid.read_text(encoding="utf-8").strip())
    except Exception:  # noqa: BLE001
        space.http_pid.unlink(missing_ok=True)
        return
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        pass
    LOG.info("Stopped pack HTTP server (pid=%s)", pid)
    space.http_pid.unlink(missing_ok=True)


def start_http_server(repo: RepoPaths, space: SpacePaths, *, port: int) -> None:
    stop_http_server(space)
    cmd = [
        sys.executable,
        str(repo.serve_pack_script),
        "--directory",
        str(space.public_dir),
        "--port",
        str(port),
    ]
    space.public_dir.mkdir(parents=True, exist_ok=True)
    with space.http_log.open("a", encoding="utf-8") as out:
        LOG.info("Starting pack HTTP server on port %s", port)
        proc = subprocess.Popen(cmd, stdout=out, stderr=out)  # noqa: S603
    space.http_pid.write_text(str(proc.pid), encoding="utf-8")
