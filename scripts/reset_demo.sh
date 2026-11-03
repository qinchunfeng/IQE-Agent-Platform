#!/usr/bin/env bash
# 仅重置 Demo 自己生成的 SQLite 数据;不触碰任何设备配置或密码。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB="$ROOT/backend/data/iqe_demo.db"

if [[ "${1:-}" != "--yes" ]]; then
  echo "该操作会删除 Demo 的 Trace / 工单 / 知识库数据。"
  echo "确认请执行:./scripts/reset_demo.sh --yes"
  exit 1
fi

if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE '(^|:)8000$'; then
  echo "检测到 8000 端口仍在监听,请先停止后端(Ctrl+C),再执行重置。" >&2
  exit 1
fi

rm -f "$DB" "$DB-wal" "$DB-shm"
echo "已重置 Demo 数据:$DB"
echo "下次启动后端会自动重建表结构并写入文档 4.2 流水线模板。"
