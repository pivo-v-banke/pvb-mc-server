from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from tomlkit.items import Table

from pivo.pack import ensure_mods_array


ALLOWED_SIDES = {"client", "server", "both"}


@dataclass(frozen=True)
class ModEntry:
    mod_id: str
    filename: str
    sha256: str
    source_url: str
    side: str


def http_get(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "pivo-cli/0.3"})
    with urlopen(req, timeout=180) as response:
        return response.read()


def sha256_stream(url: str) -> str:
    req = Request(url, headers={"User-Agent": "pivo-cli/0.3"})
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


def normalize_modrinth_download(url: str) -> str:
    if url.startswith("https://cdn.modrinth.com/"):
        return url
    if "modrinth.com/mod/" not in url or "/version/" not in url:
        return url
    html = http_get(url).decode("utf-8", errors="replace")
    match = re.search(r"https://cdn\\.modrinth\\.com/data/[^\\s\"']+\\.jar", html)
    if match:
        return match.group(0)
    raise ValueError(
        "Could not resolve Modrinth download URL from version page. "
        "Pass direct cdn.modrinth.com .jar URL instead."
    )


def guess_id(filename: str) -> str:
    base = filename[:-4] if filename.lower().endswith(".jar") else filename
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()
    return base[:64] if base else "mod"


def build_entry(url: str, *, side: str, mod_id: str | None, filename: str | None) -> ModEntry:
    if side not in ALLOWED_SIDES:
        raise ValueError(f"Invalid side: {side}")
    resolved_url = normalize_modrinth_download(url) if url.startswith("http") else url
    jar_filename = filename or filename_from_url(resolved_url)
    sha = sha256_stream(resolved_url)
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
            normalized = normalize_modrinth_download(url_or_key)
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

