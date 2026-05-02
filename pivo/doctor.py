from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from pivo.conf import SpaceConf
from pivo.docker import container_name
from pivo.pack import ensure_mods_array, read_pack
from pivo.paths import SpacePaths


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_under_mods_root(mods_root: Path, filename: str) -> Path:
    target = (mods_root / filename).resolve()
    if mods_root not in target.parents and target != mods_root:
        return (mods_root / Path(filename).name).resolve()
    return target


def _docker_ports_json(container: str) -> str | None:
    proc = subprocess.run(  # noqa: S603
        ["docker", "inspect", "-f", "{{json .NetworkSettings.Ports}}", container],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def run(space_name: str, space: SpacePaths, conf: SpaceConf) -> int:
    """Print docker mappings and sha256 checks for server/both mods vs pack.toml."""
    cname = container_name(space_name)
    mods_root = (space.data_dir / "mods").resolve()
    doc = read_pack(space.pack_toml)

    print(f"space={space_name!r}")
    print(f"pivo.conf expects clients to use {conf.server_host}:{conf.server_port} (game port)")
    print(f"container name: {cname}")

    ports_raw = _docker_ports_json(cname)
    exit_code = 0
    if ports_raw is None:
        print("docker: container not running or not inspectable — cannot show port mappings")
        exit_code = 1
    else:
        try:
            ports = json.loads(ports_raw)
            if not ports:
                print("docker: no port bindings (stopped container?)")
            else:
                for key, binds in sorted(ports.items()):
                    hosts = binds or []
                    for h in hosts:
                        print(f"docker port: {key} -> {h.get('HostIp', '?')}:{h.get('HostPort', '?')}")
        except json.JSONDecodeError:
            print(f"docker: could not parse ports: {ports_raw!r}")

    mismatches = 0
    missing = 0

    lines: list[tuple[str, str, str]] = []
    problem_lines: list[str] = []
    for mod in ensure_mods_array(doc):
        if not isinstance(mod, dict):
            continue
        side = str(mod.get("side", ""))
        if side not in {"server", "both"}:
            continue
        filename = str(mod.get("filename", ""))
        expect = str(mod.get("sha256", ""))
        mod_id = str(mod.get("id", "?"))
        path = _resolve_under_mods_root(mods_root, filename)
        if not path.is_file():
            lines.append((mod_id, filename, "MISSING"))
            problem_lines.append(f"  missing: {filename} (expected sha256={expect})")
            missing += 1
            continue
        got = _sha256_file(path)
        ok = got == expect
        tag = "ok" if ok else "mismatch"
        if not ok:
            mismatches += 1
            problem_lines.append(f"  mismatch: {filename}\n    expected={expect}\n    disk    ={got}")
        lines.append((mod_id, filename, tag))

    print("")
    print("server/both mods (pack.toml sha256 vs data/mods):")
    print(f"{'id':<48} {'status':<10} file")
    for mod_id, filename, stat in lines:
        print(f"{mod_id[:48]:<48} {stat:<10} {filename}")
    if problem_lines:
        print("")
        print("Problems:")
        print("\n".join(problem_lines))

    if missing:
        print(f"\n{missing} file(s) missing under {mods_root}")
        exit_code = 1
    if mismatches:
        print(f"\n{mismatches} sha256 mismatch(es) — run `pivo-cli -s {space_name} reload` after fixing pack")
        exit_code = 1
    if not lines:
        print("(no server/both mods in pack.toml)")

    return exit_code
