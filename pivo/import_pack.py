from __future__ import annotations

import json
import hashlib
import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

LOG = logging.getLogger(__name__)

@dataclass(frozen=True)
class ImportedMod:
    mod_id: str
    filename: str
    sha256: str
    source_url: str
    side: str


@dataclass(frozen=True)
class ImportedPack:
    name: str
    minecraft_version: str
    loader: str
    loader_version: str
    mods: list[ImportedMod]


def _http_get(url: str, *, log_request: bool) -> bytes:
    if log_request:
        LOG.info("Downloading: %s", url)
    req = Request(url, headers={"User-Agent": "pivo-cli/0.4"})
    with urlopen(req, timeout=300) as resp:
        return resp.read()


def _download_bytes(url: str) -> bytes:
    return _http_get(url, log_request=True)


def _is_url(value: str) -> bool:
    try:
        return urlparse(value).scheme in {"http", "https"}
    except Exception:  # noqa: BLE001
        return False


def _download_json(url: str) -> dict:
    return json.loads(_http_get(url, log_request=True).decode("utf-8"))


def _extract_modrinth_version_id(url: str) -> str | None:
    # https://modrinth.com/modpack/<slug>/version/<id>
    match = re.search(r"/version/([a-zA-Z0-9]+)", url)
    return match.group(1) if match else None


def _extract_modrinth_modpack_slug(url: str) -> str | None:
    # https://modrinth.com/modpack/<slug>
    match = re.search(r"/modpack/([^/?#]+)", url)
    return match.group(1) if match else None


def resolve_modrinth_mrpack_url(source: str) -> str:
    """
    Accepts:
    - direct .mrpack URL
    - Modrinth modpack page URL
    - Modrinth modpack version URL
    Returns a direct CDN URL to a .mrpack file.
    """
    if source.endswith(".mrpack") or ".mrpack?" in source:
        return source

    if "modrinth.com/modpack/" not in source:
        raise ValueError("Unsupported pack URL. Provide a Modrinth modpack URL or direct .mrpack URL.")

    version_id = _extract_modrinth_version_id(source)
    if version_id:
        LOG.info("Resolving Modrinth version: %s", version_id)
        version = _download_json(f"https://api.modrinth.com/v2/version/{version_id}")
        files = version.get("files", [])
        for f in files:
            if isinstance(f, dict) and str(f.get("filename", "")).endswith(".mrpack"):
                return str(f["url"])
        raise ValueError("No .mrpack file found for that Modrinth version.")

    slug = _extract_modrinth_modpack_slug(source)
    if not slug:
        raise ValueError("Could not parse Modrinth modpack slug.")

    LOG.info("Resolving Modrinth project: %s", slug)
    versions = _download_json(f"https://api.modrinth.com/v2/project/{slug}/version")
    if not isinstance(versions, list) or not versions:
        raise ValueError("No versions found for that Modrinth modpack.")

    # Pick latest by date_published (already sorted often, but don't rely on it).
    versions_sorted = sorted(
        [v for v in versions if isinstance(v, dict) and "date_published" in v],
        key=lambda v: str(v.get("date_published", "")),
        reverse=True,
    )
    for v in versions_sorted:
        for f in v.get("files", []):
            if isinstance(f, dict) and str(f.get("filename", "")).endswith(".mrpack"):
                return str(f["url"])

    raise ValueError("No .mrpack file found in Modrinth versions.")


def _sha256_from_modrinth_hashes(hashes: dict) -> str | None:
    # Modrinth index usually provides sha512; we can’t derive sha256 from it.
    # Some packs may include sha1 only. We require sha256 for our pipeline.
    # So we must download each mod to compute sha256 if not provided.
    if "sha256" in hashes:
        return str(hashes["sha256"])
    return None


def _guess_side(env: str | None) -> str:
    if env == "client":
        return "client"
    if env == "server":
        return "server"
    return "both"


def _extract_modrinth_project_id_from_cdn(url: str) -> str | None:
    # https://cdn.modrinth.com/data/<project_id>/versions/<version_id>/<file>
    match = re.search(r"^https://cdn\.modrinth\.com/data/([^/]+)/versions/", url)
    return match.group(1) if match else None


def _infer_side_from_modrinth_slug(slug: str) -> str | None:
    """
    Modrinth often returns client_side/server_side as "unknown". In that case we use
    conservative heuristics for obvious client-only UI mods (still best-effort).
    """
    s = slug.lower()
    needles = (
        "status-effect-bars",
        "tooltipfix",
        "chat-heads",
        "not-enough-animations",
        "entity-model-features",
        "entity-texture-features",
        "lambdynamiclights",
        "dynamic-fps",
        "zoom",
        "inventory-blur",
        "eating-animation",
        "smooth-swapping",
        "moreculling",
        "entityculling",
        "iris",
        "sodium",
        "reeses-sodium-options",
        "sodium-extra",
        "complementary",
        "shader",
        "blur",
        "detail-armor-bar",
    )
    if any(n in s for n in needles):
        return "client"
    return None


def _side_from_modrinth_project_meta(meta: dict) -> str:
    client_side = str(meta.get("client_side", "")).strip().lower()
    server_side = str(meta.get("server_side", "")).strip().lower()
    slug = str(meta.get("slug", "")).strip()

    if server_side == "unsupported" and client_side != "unsupported":
        return "client"
    if client_side == "unsupported" and server_side != "unsupported":
        return "server"

    if client_side == "unknown" and server_side == "unknown":
        return _infer_side_from_modrinth_slug(slug) or "both"

    return "both"


def _fetch_modrinth_project_sides(project_ids: list[str]) -> dict[str, str]:
    """
    Batch-resolve Modrinth project client/server support.
    Uses GET /v2/projects?ids=["id1","id2",...]
    """
    out: dict[str, str] = {}
    if not project_ids:
        return out

    chunk_size = 50
    for offset in range(0, len(project_ids), chunk_size):
        chunk = project_ids[offset : offset + chunk_size]
        ids_param = quote(json.dumps(chunk, separators=(",", ":")))
        url = f"https://api.modrinth.com/v2/projects?ids={ids_param}"
        try:
            raw = _http_get(url, log_request=False)
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            LOG.debug("Modrinth batch project fetch failed: %s", exc)
            for pid in chunk:
                out[pid] = "both"
            continue

        if not isinstance(payload, list):
            for pid in chunk:
                out[pid] = "both"
            continue

        for meta in payload:
            if not isinstance(meta, dict):
                continue
            pid = str(meta.get("id", "")).strip()
            if pid:
                out[pid] = _side_from_modrinth_project_meta(meta)

        for pid in chunk:
            out.setdefault(pid, "both")

        LOG.info(
            "Resolved Modrinth project sides (batch %s/%s, size=%s)",
            offset // chunk_size + 1,
            (len(project_ids) + chunk_size - 1) // chunk_size,
            len(chunk),
        )

    return out


def import_modrinth_mrpack(source: str) -> ImportedPack:
    data: bytes
    if _is_url(source):
        url = source
        if "modrinth.com/modpack/" in source and not source.endswith(".mrpack"):
            url = resolve_modrinth_mrpack_url(source)
        LOG.info("Importing mrpack: %s", url)
        data = _download_bytes(url)
    else:
        LOG.info("Importing mrpack from local file: %s", source)
        data = Path(source).read_bytes()

    # Avoid writing to disk: read zip from bytes.
    with zipfile.ZipFile(ZipBytes(data)) as zf:
        index = json.loads(zf.read("modrinth.index.json").decode("utf-8"))

    name = str(index.get("name", "Imported Pack"))
    deps = index.get("dependencies", {})
    minecraft_version = str(deps.get("minecraft", "")).strip()
    if not minecraft_version:
        raise ValueError("Invalid mrpack: missing dependencies.minecraft")

    loader = ""
    loader_version = ""
    for candidate in ("neoforge", "forge", "fabric-loader", "quilt-loader"):
        if candidate in deps:
            loader = candidate
            loader_version = str(deps[candidate])
            break
    if not loader:
        raise ValueError("Invalid mrpack: could not detect mod loader in dependencies")

    if loader == "fabric-loader":
        loader = "fabric"
    elif loader == "quilt-loader":
        loader = "quilt"

    files = index.get("files", [])
    if not isinstance(files, list):
        raise ValueError("Invalid mrpack: files is not a list")

    pending: list[dict[str, object]] = []
    project_ids_for_side: set[str] = set()

    for f in files:
        if not isinstance(f, dict):
            continue
        path = str(f.get("path", ""))
        if not path.startswith("mods/") or not path.endswith(".jar"):
            continue
        filename = path.split("/", 1)[1]
        env = None
        if isinstance(f.get("env"), dict):
            # env: { client: "required"/"optional"/"unsupported", server: ... }
            c = str(f["env"].get("client", "required"))
            s = str(f["env"].get("server", "required"))
            if c == "unsupported" and s != "unsupported":
                env = "server"
            elif s == "unsupported" and c != "unsupported":
                env = "client"
            else:
                env = "both"

        downloads = f.get("downloads", [])
        if not isinstance(downloads, list) or not downloads:
            raise ValueError(f"Invalid mrpack: missing downloads for {filename}")
        source_url = str(downloads[0])

        side = _guess_side(env)
        project_id = _extract_modrinth_project_id_from_cdn(source_url)
        if side == "both" and project_id:
            project_ids_for_side.add(project_id)

        hashes = f.get("hashes", {})
        pending.append(
            {
                "filename": filename,
                "source_url": source_url,
                "side": side,
                "project_id": project_id,
                "hashes": hashes,
            }
        )

    project_side_cache = _fetch_modrinth_project_sides(sorted(project_ids_for_side))

    mods: list[ImportedMod] = []
    for item in pending:
        filename = str(item["filename"])
        source_url = str(item["source_url"])
        side = str(item["side"])
        project_id = item.get("project_id")
        hashes = item.get("hashes", {})

        if side == "both" and isinstance(project_id, str) and project_id:
            side = project_side_cache.get(project_id, "both")

        sha256 = _sha256_from_modrinth_hashes(hashes) if isinstance(hashes, dict) else None
        sha256 = sha256 or ""
        mod_id = filename.rsplit(".", 1)[0]

        if not sha256:
            LOG.debug("Computing sha256: %s", source_url)
            sha256 = _compute_sha256(source_url)

        mods.append(
            ImportedMod(
                mod_id=mod_id,
                filename=filename,
                sha256=sha256,
                source_url=source_url,
                side=side,
            )
        )

    return ImportedPack(
        name=name,
        minecraft_version=minecraft_version,
        loader=loader,
        loader_version=loader_version,
        mods=mods,
    )


class ZipBytes:
    # Minimal file-like wrapper for zipfile.
    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            n = len(self._data) - self._pos
        out = self._data[self._pos : self._pos + n]
        self._pos += len(out)
        return out

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = len(self._data) + offset
        else:
            raise ValueError("Invalid whence")
        return self._pos

    def tell(self) -> int:
        return self._pos

    def seekable(self) -> bool:
        return True


def _compute_sha256(url: str) -> str:
    req = Request(url, headers={"User-Agent": "pivo-cli/0.4"})
    digest = hashlib.sha256()
    LOG.info("Downloading for sha256: %s", url)
    with urlopen(req, timeout=300) as resp:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()

