from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from tomlkit.items import Table

from pivo.pack import ensure_mods_array


ALLOWED_SIDES = {"client", "server", "both"}

# Modrinth CDN и API отклоняют типичный Python-urllib без нормального User-Agent.
_REQUEST_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"


@dataclass(frozen=True)
class ModEntry:
    mod_id: str
    filename: str
    sha256: str
    source_url: str
    side: str


def http_get(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": _REQUEST_UA, "Accept": "*/*"})
    with urlopen(req, timeout=180) as response:
        return response.read()


def sha256_stream(url: str) -> str:
    req = Request(url, headers={"User-Agent": _REQUEST_UA, "Accept": "*/*"})
    digest = hashlib.sha256()
    with urlopen(req, timeout=180) as response:
        while True:
            buf = response.read(1024 * 1024)
            if not buf:
                break
            digest.update(buf)
    return digest.hexdigest()


def filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name
    if not name:
        raise ValueError(f"Could not infer filename from URL: {url}")
    return name


_MODRINTH_MOD_RE = re.compile(
    r"^https?://(?:www\.)?modrinth\.com/(?:app/)?mod/([^/]+)(?:/version/([^/?#]+))?/?(?:\?.*)?$",
    re.IGNORECASE,
)


def _modrinth_get_json(api_path: str) -> Any:
    u = f"https://api.modrinth.com/v2{api_path}"
    req = Request(u, headers={"User-Agent": _REQUEST_UA, "Accept": "application/json"})
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def _jar_from_modrinth_version(ver: dict) -> tuple[str, str | None, str | None]:
    """Возвращает (cdn_url, filename, sha256 или None)."""
    files = ver.get("files") or []
    candidates = list(files)
    primary = next((f for f in candidates if f.get("primary")), None)
    jar = primary or next((f for f in candidates if str(f.get("filename", "")).endswith(".jar")), None)
    if not jar:
        raise ValueError("Modrinth version has no .jar file in API response")
    u = str(jar.get("url") or "")
    if not u.startswith("https://cdn.modrinth.com/"):
        raise ValueError(f"Unexpected Modrinth file URL: {u!r}")
    fn = str(jar.get("filename") or "") or None
    hashes = jar.get("hashes") if isinstance(jar.get("hashes"), dict) else {}
    sha = hashes.get("sha256") if isinstance(hashes, dict) else None
    sha = str(sha) if sha else None
    return u, fn, sha


def resolve_modrinth_url(
    url: str,
    *,
    game_version: str | None = None,
    loader: str | None = None,
    loose: bool = False,
) -> tuple[str, str | None]:
    """
    Ссылки modrinth.com → (cdn .jar URL, sha256 из API или None).
    loose=True: страница /mod/<slug> без версии и без game/loader — вернуть URL как есть (для remove-mod).
    """
    u = (url or "").strip()
    if u.startswith("https://cdn.modrinth.com/"):
        return u, None

    m = _MODRINTH_MOD_RE.match(u)
    if not m:
        cdn_guess = _modrinth_cdn_from_version_html_page(u)
        return (cdn_guess if cdn_guess else u), None

    slug, version_id = m.group(1), m.group(2)

    if version_id:
        ver = _modrinth_get_json(f"/version/{quote(version_id, safe='')}")
        jar_url, _fn, sha = _jar_from_modrinth_version(ver)
        return jar_url, sha

    if not game_version or not loader:
        if loose:
            return u, None
        raise ValueError(
            "Ссылка вида https://modrinth.com/mod/<slug> без /version/…: "
            "нужны minecraft_version и loader из [pack] (добавляйте через `pivo-cli -s <space> add-mod …`) "
            "или укажите прямую ссылку на .jar с cdn.modrinth.com."
        )

    q = (
        f"?game_versions={quote(json.dumps([game_version]))}"
        f"&loaders={quote(json.dumps([loader]))}"
    )
    versions = _modrinth_get_json(f"/project/{quote(slug, safe='')}/version{q}")
    if not isinstance(versions, list) or not versions:
        raise ValueError(
            f"Modrinth: нет версии для «{slug}» с game_versions={game_version!r} и loaders={loader!r}. "
            "Проверьте slug, версию Minecraft и лоадер в pack.toml."
        )
    jar_url, _fn, sha = _jar_from_modrinth_version(versions[0])
    return jar_url, sha


def normalize_modrinth_download(
    url: str,
    *,
    game_version: str | None = None,
    loader: str | None = None,
    loose: bool = False,
) -> str:
    """Только URL (совместимость с remove-mod и старым кодом)."""
    resolved, _ = resolve_modrinth_url(
        url, game_version=game_version, loader=loader, loose=loose
    )
    return resolved


def _modrinth_cdn_from_version_html_page(url: str) -> str | None:
    if "modrinth.com/mod/" not in url or "/version/" not in url:
        return None
    html = http_get(url).decode("utf-8", errors="replace")
    match = re.search(r"https://cdn\.modrinth\.com/data/[^\s\"']+\.jar", html)
    return match.group(0) if match else None


def guess_id(filename: str) -> str:
    base = filename[:-4] if filename.lower().endswith(".jar") else filename
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()
    return base[:64] if base else "mod"


def build_entry(
    url: str,
    *,
    side: str,
    mod_id: str | None,
    filename: str | None,
    game_version: str | None = None,
    loader: str | None = None,
) -> ModEntry:
    if side not in ALLOWED_SIDES:
        raise ValueError(f"Invalid side: {side}")
    if url.startswith("http"):
        resolved_url, api_sha = resolve_modrinth_url(
            url, game_version=game_version, loader=loader, loose=False
        )
    else:
        resolved_url, api_sha = url, None
    jar_filename = filename or filename_from_url(resolved_url)
    sha = api_sha if api_sha else sha256_stream(resolved_url)
    entry_id = mod_id or guess_id(jar_filename)
    return ModEntry(
        mod_id=entry_id,
        filename=jar_filename,
        sha256=sha,
        source_url=resolved_url,
        side=side,
    )


def add_mod(doc: Table, entry: ModEntry) -> bool:
    mods = ensure_mods_array(doc)
    for mod in mods:
        if isinstance(mod, dict) and mod.get("source_url") == entry.source_url:
            mod["id"] = entry.mod_id
            mod["filename"] = entry.filename
            mod["sha256"] = entry.sha256
            mod["side"] = entry.side
            return False

    mods.append(
        {
            "id": entry.mod_id,
            "filename": entry.filename,
            "sha256": entry.sha256,
            "source_url": entry.source_url,
            "side": entry.side,
        }
    )
    return True


def remove_mod(doc: Table, url_or_key: str) -> int:
    mods = ensure_mods_array(doc)
    before = len(mods)
    normalized = url_or_key
    if url_or_key.startswith("http"):
        try:
            normalized = normalize_modrinth_download(url_or_key, loose=True)
        except Exception:  # noqa: BLE001
            normalized = url_or_key

    def keep(mod: Any) -> bool:
        if not isinstance(mod, dict):
            return True
        if mod.get("source_url") == normalized:
            return False
        if mod.get("filename") == url_or_key:
            return False
        if mod.get("id") == url_or_key:
            return False
        return True

    filtered = [m for m in mods if keep(m)]
    doc["mods"] = filtered
    return before - len(filtered)


def format_mods_table(doc: Table) -> str:
    mods = ensure_mods_array(doc)
    rows: list[tuple[str, str, str, str]] = []
    for mod in mods:
        if not isinstance(mod, dict):
            continue
        rows.append(
            (
                str(mod.get("id", "")),
                str(mod.get("side", "")),
                str(mod.get("filename", "")),
                str(mod.get("source_url", "")),
            )
        )
    if not rows:
        return ""

    widths = [0, 0, 0, 0]
    for row in rows:
        for i, col in enumerate(row):
            widths[i] = max(widths[i], len(col))

    header = ("id", "side", "filename", "source_url")
    widths = [max(widths[i], len(header[i])) for i in range(4)]
    out: list[str] = []
    out.append(
        f"{header[0]:<{widths[0]}}  {header[1]:<{widths[1]}}  "
        f"{header[2]:<{widths[2]}}  {header[3]}"
    )
    out.append("-" * (sum(widths) + 6))
    for row in rows:
        out.append(
            f"{row[0]:<{widths[0]}}  {row[1]:<{widths[1]}}  "
            f"{row[2]:<{widths[2]}}  {row[3]}"
        )
    out.append("")
    return "\n".join(out)

