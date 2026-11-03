#!/usr/bin/env bash
# 文档 0.4:后端端口 8000
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

if ! command -v uv >/dev/null 2>&1; then
  echo "未找到 uv,请先安装:https://docs.astral.sh/uv/" >&2
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "创建 Python 3.12 虚拟环境..."
  uv venv --python 3.12 .venv
  uv pip install --python .venv/bin/python -r requirements.txt
fi

echo "后端启动:http://127.0.0.1:8000 (OpenAPI: /docs)"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
