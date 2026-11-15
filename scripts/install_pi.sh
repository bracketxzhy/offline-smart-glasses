#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
python3 - <<'PY'
import platform,sys
if platform.machine() not in {"aarch64","arm64"} or sys.version_info[:2] != (3,13):
    raise SystemExit("This offline bundle requires Linux ARM64 and Python 3.13; rebuild the wheelhouse for other versions.")
PY
python3 -m venv .ai-env
.ai-env/bin/python -m pip install --no-index --find-links wheelhouse/linux-aarch64-cp313 -r requirements-runtime.txt
find runtime/llama -type f -name 'llama*' -exec chmod u+x {} +
.ai-env/bin/python scripts/check_install.py
echo 'Installed offline. Start: .ai-env/bin/python scripts/run.py start'
echo 'Control panel: http://127.0.0.1:8765'
