from __future__ import annotations

import datetime as dt
import shutil

from pivo.paths import SpacePaths


def create_backup(space: SpacePaths) -> str:
    space.backups_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = space.backups_dir / f"backup-{ts}.tar.gz"
    base = space.root.name
    archive_base = out.with_suffix("").with_suffix("")
    shutil.make_archive(str(archive_base), "gztar", root_dir=space.root.parent, base_dir=base)
    return str(out)

