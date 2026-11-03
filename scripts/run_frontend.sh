#!/usr/bin/env bash
# 文档 0.4:前端端口 3200(Vite 默认 5173/5174 已被占用)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/frontend"

if ! command -v npm >/dev/null 2>&1; then
  echo "未找到 npm,请先安装 Node.js 22+" >&2
  exit 1
fi

if [[ ! -d node_modules ]]; then
  echo "安装前端依赖..."
  npm install --no-audit --no-fund
fi

echo "前端启动:http://127.0.0.1:3200"
exec npm run dev
