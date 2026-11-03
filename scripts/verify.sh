#!/usr/bin/env bash
# 验收:后端 40 项测试 + 前端类型检查/构建
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> backend pytest"
cd "$ROOT/backend"
.venv/bin/pytest -q

echo "==> frontend build"
cd "$ROOT/frontend"
npm run build
