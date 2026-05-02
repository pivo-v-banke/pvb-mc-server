from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import sys
import tomllib
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class SpaceInfo:
    name: str
    minecraft_version: str
    loader: str
    loader_version: str
    server_port: int
    server_host: str | None
    display_name: str | None
    description_markdown: str


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--spaces-dir", default=os.environ.get("PIVO_SPACES_DIR", "/spaces"))
    return parser.parse_args(argv)


def safe_join(base: Path, *parts: str) -> Path:
    out = base
    for part in parts:
        part = part.replace("\\", "/")
        part = posixpath.normpath(part)
        if part.startswith("../") or part == ".." or part.startswith("/"):
            raise ValueError("Invalid path traversal")
        out = out / part
    return out


def read_space_info(space_dir: Path, name: str) -> SpaceInfo | None:
    pack_path = space_dir / "pack.toml"
    conf_path = space_dir / "pivo.conf"
    if not pack_path.exists() or not conf_path.exists():
        return None

    pack_data = tomllib.loads(pack_path.read_text(encoding="utf-8"))
    pack = pack_data.get("pack", {})
    minecraft_version = str(pack.get("minecraft_version", "")).strip()
    loader = str(pack.get("loader", "")).strip()
    loader_version = str(pack.get("loader_version", "")).strip()

    server_port = 25565
    server_host: str | None = None
    display_name: str | None = None
    for raw in conf_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k == "SERVER_PORT":
            try:
                server_port = int(v)
            except ValueError:
                server_port = 25565
        if k == "SERVER_HOST":
            server_host = v or None
        if k == "SPACE_DISPLAY_NAME":
            display_name = v or None

    description_md = ""
    desc_path = space_dir / "description.md"
    if desc_path.exists():
        description_md = desc_path.read_text(encoding="utf-8")

    if not minecraft_version or not loader:
        return None

    return SpaceInfo(
        name=name,
        minecraft_version=minecraft_version,
        loader=loader,
        loader_version=loader_version,
        server_port=server_port,
        server_host=server_host,
        display_name=display_name,
        description_markdown=description_md,
    )


def read_pack_mods(space_dir: Path) -> list[dict]:
    pack_path = space_dir / "pack.toml"
    if not pack_path.exists():
        return []
    pack_data = tomllib.loads(pack_path.read_text(encoding="utf-8"))
    mods = pack_data.get("mods", [])
    return mods if isinstance(mods, list) else []


def ensure_lock_file(space_dir: Path, name: str) -> Path:
    public_dir = space_dir / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    lock_path = public_dir / "pack.lock.toml"
    if lock_path.exists():
        return lock_path

    pack_data = tomllib.loads((space_dir / "pack.toml").read_text(encoding="utf-8"))
    pack = pack_data["pack"]

    lines: list[str] = []
    lines.append("[pack]")
    lines.append(f'name = "{pack.get("name", name)}"')
    lines.append(f'minecraft_version = "{pack["minecraft_version"]}"')
    lines.append(f'loader = "{pack["loader"]}"')
    lines.append(f'loader_version = "{pack.get("loader_version", "")}"')
    lines.append("")

    for mod in read_pack_mods(space_dir):
        if not isinstance(mod, dict):
            continue
        lines.append("[[mods]]")
        lines.append(f'id = "{mod["id"]}"')
        lines.append(f'filename = "{mod["filename"]}"')
        lines.append(f'sha256 = "{mod["sha256"]}"')
        lines.append(f'side = "{mod["side"]}"')
        lines.append(f'url = "/spaces/{name}/mods/{mod["filename"]}"')
        lines.append("")

    lock_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return lock_path


def ensure_mod_file(space_dir: Path, filename: str) -> Path | None:
    mods_dir = space_dir / "public" / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    target = safe_join(mods_dir, filename)
    if target.exists():
        return target

    entries = [m for m in read_pack_mods(space_dir) if isinstance(m, dict)]
    entry = next((m for m in entries if m.get("filename") == filename), None)
    if not entry:
        return None

    source_url = str(entry.get("source_url", "")).strip()
    expected_sha = str(entry.get("sha256", "")).strip()
    if not source_url or not expected_sha:
        return None

    target.parent.mkdir(parents=True, exist_ok=True)
    req = Request(source_url, headers={"User-Agent": "pivo-hub/0.1"})
    digest = __import__("hashlib").sha256()
    with urlopen(req, timeout=180) as response:
        with target.open("wb") as out:
            while True:
                buf = response.read(1024 * 1024)
                if not buf:
                    break
                digest.update(buf)
                out.write(buf)
    if digest.hexdigest() != expected_sha:
        target.unlink(missing_ok=True)
        raise ValueError("sha256 mismatch for downloaded mod")

    return target


def list_spaces(spaces_root: Path) -> list[SpaceInfo]:
    if not spaces_root.exists():
        return []
    out: list[SpaceInfo] = []
    for child in sorted(spaces_root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        info = read_space_info(child, child.name)
        if info:
            out.append(info)
    return out


class HubHandler(BaseHTTPRequestHandler):
    server_version = "pivo-hub/0.1"

    def _json(self, status: int, payload: object) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _text(self, status: int, text: str) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path) -> None:
        data = path.read_bytes()
        content_type = "application/octet-stream"
        if path.name.endswith(".toml"):
            content_type = "application/toml; charset=utf-8"
        if path.name.endswith(".jar"):
            content_type = "application/java-archive"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    @property
    def spaces_root(self) -> Path:
        return Path(self.server.spaces_dir)  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/healthz":
            self._text(200, "ok\n")
            return

        if path == "/api/spaces":
            spaces = list_spaces(self.spaces_root)
            payload = {
                "spaces": [
                    {
                        "name": s.name,
                        "display_name": (s.display_name or s.name),
                        "description_markdown": s.description_markdown,
                        "pack": {
                            "minecraft_version": s.minecraft_version,
                            "loader": s.loader,
                            "loader_version": s.loader_version,
                        },
                        "server": {
                            "host": s.server_host,
                            "port": s.server_port,
                        },
                        "endpoints": {
                            "lock": f"/spaces/{s.name}/pack.lock.toml",
                            "mods_base": f"/spaces/{s.name}/mods/",
                        },
                    }
                    for s in spaces
                ]
            }
            self._json(200, payload)
            return

        match = re.fullmatch(r"/api/spaces/([a-zA-Z0-9_.-]+)", path)
        if match:
            name = match.group(1)
            info = read_space_info(self.spaces_root / name, name)
            if not info:
                self._json(404, {"error": "space_not_found"})
                return
            payload = {
                "name": info.name,
                "display_name": (info.display_name or info.name),
                "description_markdown": info.description_markdown,
                "pack": {
                    "minecraft_version": info.minecraft_version,
                    "loader": info.loader,
                    "loader_version": info.loader_version,
                },
                "server": {"host": info.server_host, "port": info.server_port},
                "endpoints": {
                    "lock": f"/spaces/{info.name}/pack.lock.toml",
                    "mods_base": f"/spaces/{info.name}/mods/",
                },
            }
            self._json(200, payload)
            return

        match = re.fullmatch(r"/spaces/([a-zA-Z0-9_.-]+)/pack\.lock\.toml", path)
        if match:
            name = match.group(1)
            try:
                space_dir = safe_join(self.spaces_root, name)
            except ValueError:
                self._json(400, {"error": "bad_path"})
                return
            try:
                lock_path = ensure_lock_file(space_dir, name)
            except Exception:  # noqa: BLE001
                self._json(500, {"error": "lock_generation_failed"})
                return
            self._file(lock_path)
            return

        match = re.fullmatch(r"/spaces/([a-zA-Z0-9_.-]+)/mods/(.+)", path)
        if match:
            name = match.group(1)
            rel = unquote(match.group(2))
            try:
                space_dir = safe_join(self.spaces_root, name)
            except ValueError:
                self._json(400, {"error": "bad_path"})
                return
            try:
                # allow nested paths, but forbid traversal/absolute
                _ = safe_join(Path("."), rel)
            except ValueError:
                self._json(400, {"error": "bad_path"})
                return
            try:
                mod_path = ensure_mod_file(space_dir, rel)
            except ValueError:
                self._json(500, {"error": "mod_sha256_mismatch"})
                return
            if not mod_path:
                self._json(404, {"error": "mod_not_found"})
                return
            self._file(mod_path)
            return

        self._json(404, {"error": "not_found"})


class HubHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler: type[BaseHTTPRequestHandler], *, spaces_dir: str):
        super().__init__(server_address, handler)
        self.spaces_dir = spaces_dir


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    server = HubHTTPServer((args.host, args.port), HubHandler, spaces_dir=str(args.spaces_dir))
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

