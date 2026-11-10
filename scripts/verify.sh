#!/usr/bin/env bash
# 三层终止检查：第 N 层不通过就不许进第 N+1 层（见 AGENTS.md「怎么算完成」）。
#   层 1 静态     ruff / mypy / eslint / tsc
#   层 2 单元集成 后端 pytest（57 项）+ 前端 vite build
#   层 3 运行时   scripts/smoke_test.py 起真实进程跑场景 1 与场景 2
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
START=$SECONDS

die() {
  printf '\nERROR  %s\nWHY    %s\nFIX    %s\n' "$1" "$2" "$3" >&2
  exit 1
}

step() { printf '\n==> %s\n' "$1"; }

# ---------------------------------------------------------------- 层 1 静态
step "层 1/3 静态检查 :: ruff (backend + scripts)"
cd "$ROOT"
[ -x backend/.venv/bin/ruff ] || die "层 1 缺 ruff" \
  "backend/.venv 里没装静态检查工具链" \
  "uv pip install -p backend/.venv/bin/python -r backend/requirements-dev.txt"
backend/.venv/bin/ruff check backend scripts || die "层 1 Python lint" \
  "ruff 报告违规（规则集见根目录 ruff.toml，覆盖 backend 与 scripts）" \
  "优先改代码；只有确属误报才在 ruff.toml 里加豁免，并写明理由"

step "层 1/3 静态检查 :: backend mypy"
cd "$ROOT/backend"
[ -x .venv/bin/mypy ] || die "层 1 缺 mypy" \
  "backend/.venv 里没装静态检查工具链" \
  "uv pip install -p backend/.venv/bin/python -r backend/requirements-dev.txt"
.venv/bin/mypy app || die "层 1 后端类型检查" \
  "mypy 报告类型错误（已收口的模块见 backend/mypy.ini，豁免清单在文件头）" \
  "新代码必须满足类型；扩豁免前先确认不是 FEATURES.md Task 24 已登记的债"

step "层 1/3 静态检查 :: frontend eslint"
cd "$ROOT/frontend"
[ -d node_modules ] || die "层 1 缺前端依赖" \
  "frontend/node_modules 不存在，eslint 无法运行" \
  "cd frontend && npm install（或直接跑一次 ./scripts/run_frontend.sh）"
npm run --silent lint || die "层 1 前端 lint" \
  "eslint 报告 error（规则集见 frontend/eslint.config.js）" \
  "warning 不阻断，error 必须修"

step "层 1/3 静态检查 :: frontend tsc"
npm run --silent typecheck || die "层 1 前端类型检查" \
  "tsc -b 报告类型错误" \
  "tsconfig.app.json 是 strict + noUnusedLocals，按报错行修"

# ---------------------------------------------------------- 层 2 单元/集成
step "层 2/3 单元与集成 :: backend pytest"
cd "$ROOT/backend"
.venv/bin/pytest -q || die "层 2 后端测试" \
  "pytest 未全绿（用例清单见 backend/tests/）" \
  "先定位是功能回归还是用例过期；改测试必须在 FEATURES.md 对应任务里留原因"

step "层 2/3 前端构建 :: tsc + vite build"
cd "$ROOT/frontend"
npm run --silent build || die "层 2 前端构建" \
  "vite build 失败" \
  "看构建输出的第一个模块错误"

# ------------------------------------------------------------ 层 3 运行时
step "层 3/3 运行时冒烟 :: 真实进程端到端"
cd "$ROOT"
backend/.venv/bin/python scripts/smoke_test.py || die "层 3 运行时冒烟" \
  "真实 uvicorn 进程下场景 1 或场景 2 没跑通（含死信与非空失败 Run 检查）" \
  "冒烟输出里的 ERROR/WHY/FIX 已定位到阶段；它用临时库，可放心重跑"

printf '\nVERIFY OK  三层全部通过，用时 %ss\n' "$((SECONDS - START))"
