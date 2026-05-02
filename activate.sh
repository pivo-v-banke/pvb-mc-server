#!/usr/bin/env bash
# Создаёт .venv, ставит зависимости из requirements.txt и запускает интерактивный bash с активированным venv.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi

./.venv/bin/pip install -U pip >/dev/null
./.venv/bin/pip install -r requirements.txt

# shellcheck source=/dev/null
source .venv/bin/activate

exec bash -i
