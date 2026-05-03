from __future__ import annotations

import argparse
import logging
import subprocess
from pathlib import Path

from pivo import backup, doctor, docker, mods, pack, spaces, sync
from pivo.conf import SpaceConf
from pivo.import_pack import import_modrinth_mrpack
from pivo.logging_utils import setup_logging
from pivo.paths import RepoPaths

LOG = logging.getLogger(__name__)

def build_parser(repo: RepoPaths) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pivo-cli")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("-s", "--space", help="Space name")

    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create-space", help="Create a new server space")
    create.add_argument("space_name")
    create.add_argument(
        "--template-pack",
        default=str(repo.template_pack),
        help="Template pack.toml path (default: repo pack.toml)",
    )
    create.add_argument(
        "--from-pack",
        help="Import Modrinth .mrpack (URL or local file) and generate pack.toml",
    )

    hub = sub.add_parser("start-hub", help="Start hub for listing spaces")
    hub.add_argument("-p", "--port", type=int, required=True)

    sub.add_parser("start", help="Start server for a space")
    sub.add_parser("stop", help="Stop server for a space")
    sub.add_parser("reload", help="Sync mods and restart server")

    sub.add_parser("rcon", help="Open RCON console (interactive)")
    sub.add_parser("rocn", help="Alias for rcon")

    logs_cmd = sub.add_parser("logs", help="Read server logs")
    logs_cmd.add_argument("-f", "--follow", action="store_true")
    logs_cmd.add_argument("--tail", default="200")

    sub.add_parser("backup", help="Create a backup of the space")

    sub.add_parser(
        "doctor",
        help="Show docker port mappings and sha256 of server/both mods vs pack.toml",
    )

    add = sub.add_parser("add-mod", help="Add mod by URL and compute sha256")
    add.add_argument("url")
    add.add_argument("--side", default="both", choices=sorted(mods.ALLOWED_SIDES))
    add.add_argument("--id", dest="mod_id")
    add.add_argument("--filename")

    rm = sub.add_parser("remove-mod", help="Remove mod by URL (or filename/id)")
    rm.add_argument("url_or_key")

    ls = sub.add_parser("list-mods", help="List mods from pack.toml")
    ls.add_argument("--format", choices=["table", "toml"], default="table")

    return parser


def main(argv: list[str]) -> int:
    repo = RepoPaths(root=Path(__file__).resolve().parent.parent)
    spaces.ensure_repo_layout(repo)
    parser = build_parser(repo)
    args = parser.parse_args(argv)
    setup_logging(verbose=bool(getattr(args, "verbose", False)), quiet=bool(getattr(args, "quiet", False)))
    LOG.debug("argv=%s", argv)

    if args.cmd == "create-space":
        template = Path(args.template_pack).resolve()
        if args.from_pack:
            LOG.info("Importing pack from %s", args.from_pack)
            imported = import_modrinth_mrpack(args.from_pack)
            tpl = template if template.exists() else None
            if tpl is None:
                LOG.info(
                    "Template pack not found at %s — using built-in stub (mrpack overwrites it)",
                    template,
                )
            space = spaces.create_space(repo, args.space_name, template_pack=tpl)
            doc = pack.read_pack(space.pack_toml)
            doc["pack"]["name"] = imported.name
            doc["pack"]["minecraft_version"] = imported.minecraft_version
            doc["pack"]["loader"] = imported.loader
            doc["pack"]["loader_version"] = imported.loader_version
            doc["mods"] = [
                {
                    "id": m.mod_id,
                    "filename": m.filename,
                    "sha256": m.sha256,
                    "source_url": m.source_url,
                    "side": m.side,
                }
                for m in imported.mods
            ]
            pack.write_pack(space.pack_toml, doc)
        else:
            space = spaces.create_space(repo, args.space_name, template_pack=template)
        print(f"Created space: {args.space_name} ({space.root})")
        return 0

    if args.cmd == "start-hub":
        LOG.info("Building hub image")
        docker_image = "pivo-hub:latest"
        build = [
            "docker",
            "build",
            "-t",
            docker_image,
            "-f",
            str(repo.root / "hub" / "Dockerfile"),
            str(repo.root),
        ]
        subprocess.run(build, check=True, text=True)  # noqa: S603

        LOG.info("Starting hub container on port %s", args.port)
        subprocess.run(["docker", "rm", "-f", "pivo-hub"], check=False, text=True)  # noqa: S603
        run = [
            "docker",
            "run",
            "-d",
            "--name",
            "pivo-hub",
            "-p",
            f"{args.port}:8088",
            "-v",
            f"{repo.spaces_dir}:/spaces",
            docker_image,
            "--port",
            "8088",
            "--spaces-dir",
            "/spaces",
        ]
        subprocess.run(run, check=True, text=True)  # noqa: S603
        print(f"Hub started on port {args.port}")
        return 0

    space = spaces.require_space(repo, args.space)
    conf = SpaceConf.from_file(space.conf)
    LOG.debug("space=%s root=%s", args.space, space.root)
    LOG.info(
        "Ports: minecraft=%s:%s rcon=%s hub_public=http://%s:%s",
        conf.server_host,
        conf.server_port,
        conf.rcon_port,
        conf.hub_public_host,
        conf.hub_public_port,
    )

    if args.cmd in {"add-mod", "remove-mod", "list-mods", "start", "reload"}:
        doc = pack.read_pack(space.pack_toml)

    if args.cmd == "add-mod":
        LOG.info("Adding mod: %s", args.url)
        pinfo = pack.get_pack_info(doc)
        entry = mods.build_entry(
            args.url,
            side=args.side,
            mod_id=args.mod_id,
            filename=args.filename,
            game_version=pinfo.minecraft_version,
            loader=pinfo.loader,
        )
        created = mods.add_mod(doc, entry)
        pack.write_pack(space.pack_toml, doc)
        action = "Added" if created else "Updated"
        print(f"{action}: {entry.mod_id} ({entry.filename})")
        return 0

    if args.cmd == "remove-mod":
        LOG.info("Removing mod: %s", args.url_or_key)
        removed = mods.remove_mod(doc, args.url_or_key)
        pack.write_pack(space.pack_toml, doc)
        print(f"Removed: {removed}")
        return 0

    if args.cmd == "list-mods":
        if args.format == "toml":
            for mod in pack.ensure_mods_array(doc):
                if isinstance(mod, dict):
                    print(mod)
            return 0
        print(mods.format_mods_table(doc), end="")
        return 0

    if args.cmd == "start":
        LOG.info("Starting space: %s", args.space)
        sync.apply_jvm_args(space)
        sync.sync_mods(repo, space, conf)
        docker.start(args.space, space, pack.get_pack_info(doc), conf)
        return 0

    if args.cmd == "stop":
        LOG.info("Stopping space: %s", args.space)
        docker.stop(args.space)
        return 0

    if args.cmd == "reload":
        LOG.info("Reloading space: %s", args.space)
        sync.apply_jvm_args(space)
        sync.sync_mods(repo, space, conf)
        # restart не подхватывает новые -e из jvm.args; itzg и так перезаписывает
        # user_jvm_args.txt из INIT_MEMORY/MAX_MEMORY при каждом старте.
        docker.start(args.space, space, pack.get_pack_info(doc), conf)
        return 0

    if args.cmd == "logs":
        LOG.info("Reading logs: %s", args.space)
        return docker.logs(args.space, follow=bool(args.follow), tail=str(args.tail))

    if args.cmd in {"rcon", "rocn"}:
        LOG.info("Opening RCON: %s", args.space)
        return docker.rcon(args.space)

    if args.cmd == "backup":
        LOG.info("Creating backup: %s", args.space)
        print(backup.create_backup(space))
        return 0

    if args.cmd == "doctor":
        return doctor.run(args.space, space, conf)

    raise ValueError(f"Unknown command: {args.cmd}")

