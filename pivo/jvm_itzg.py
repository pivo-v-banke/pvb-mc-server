"""Сопоставление jvm.args с переменными itzg/minecraft-server.

Образ при запуске генерирует /data/user_jvm_args.txt из MEMORY / INIT_MEMORY /
MAX_MEMORY и может затереть то, что записал pivo — см. документацию itzg
(configuration/jvm-options, Memory Limit).
"""

from __future__ import annotations

from pathlib import Path


def jvm_args_to_itzg_env(jvm_args_path: Path) -> dict[str, str]:
    """
    Вернуть пары ключ=значение для docker -e … (только непустые).

    - При наличии и -Xms, и -Xmx: INIT_MEMORY, MAX_MEMORY
    - Только -Xmx: MEMORY (itzg выставит и начальный, и максимальный куч)
    - Только -Xms: INIT_MEMORY
    - Прочие токены (Aikar, -XX:…, -D…): JVM_OPTS одной строкой
    """
    out: dict[str, str] = {}
    if not jvm_args_path.exists():
        return out

    xms_val: str | None = None
    xmx_val: str | None = None
    extras: list[str] = []

    for line in jvm_args_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        for tok in s.split():
            if tok.startswith("-Xms"):
                v = tok[4:].strip()
                xms_val = v or None
            elif tok.startswith("-Xmx"):
                v = tok[4:].strip()
                xmx_val = v or None
            else:
                extras.append(tok)

    if xms_val and xmx_val:
        out["INIT_MEMORY"] = xms_val
        out["MAX_MEMORY"] = xmx_val
        # В образе часто задано MEMORY=1G; иначе скрипты itzg могут оставить дефолт.
        out["MEMORY"] = ""
    elif xmx_val:
        out["MEMORY"] = xmx_val
    elif xms_val:
        out["INIT_MEMORY"] = xms_val

    if extras:
        out["JVM_OPTS"] = " ".join(extras)

    return out
