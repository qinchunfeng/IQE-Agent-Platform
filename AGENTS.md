# AGENTS.md

IQE-Agent Platform Demo 的入口文件。**只做目录，不做百科全书**——需要细节时按下面的索引去读专题文档。

## 这是什么

面向管理层演示的插件化 AI Agent 编排平台：平台内核只做编排，输入源 / Agent / 知识库 / 工具 / 编排引擎 / LLM / 事件总线 / 存储全部可插拔。
链路为 Monitor → Triage → Reproduction → Ticket → Reviewer → Reporting。

| 项 | 值 |
|---|---|
| 后端 | Python 3.12、FastAPI、Pydantic v2、asyncio、httpx、SQLite |
| 前端 | React 18、TypeScript、Vite |
| 端口 | 前端 3200、后端 8000（绑 `127.0.0.1`）、Airflow 18080 |
| 代码根 | `backend/app/`（41 个 py）、`frontend/src/`（8 个页面） |

## 首次运行

```bash
./scripts/run_backend.sh    # 自动 uv venv + 装依赖，起在 :8000
./scripts/run_frontend.sh   # 自动 npm install，起在 :3200
./scripts/verify.sh         # 三层验收（见"怎么算完成"）
./scripts/reset_demo.sh --yes   # 只删 Demo 自己生成的 DB，不碰外部配置
```

## 怎么算完成

`./scripts/verify.sh` 三层逐层 gating，任一层失败即未完成（第 N 层不过就不跑第 N+1 层）：

1. **静态**：`ruff`（覆盖 `backend/` + `scripts/`）+ 后端 `mypy` + 前端 `eslint` + `tsc -b`
2. **单元/集成**：后端 `pytest`（57 项）+ 前端 `vite build`
3. **运行时**：`scripts/smoke_test.py` 起真实后端进程跑场景 1（自动完成）与场景 2（人工卡点 → 批准）

文档另跑 `backend/.venv/bin/python scripts/check_docs.py`（链接可解析、状态文件已入库、进度未落后于代码）。
静态工具装法：`uv pip install -p backend/.venv/bin/python -r backend/requirements-dev.txt`。

## 现在开始工作（会话开始例程）

1. 读 `PROGRESS.md` — 做到哪、卡在哪、下一步是什么
2. **复核其"已知问题/卡点"是否仍在代码里成立**（grep 或跑对应测试）；已撤销或已修复的当场标注判定依据，不要照着陈旧阻塞项干活
3. 读 `FEATURES.md` — 选**一个**未完成任务（WIP=1），看它的验收标准与依赖
4. 跑 `./scripts/verify.sh` — 确认起点是绿的，再动手

## 收工前必须（会话结束例程）

1. 更新 `PROGRESS.md`（快照 / 进行中 / 已知问题 / 下一步 / 验证记录）
2. 勾选 `FEATURES.md` 中已通过验证的任务
3. `./scripts/verify.sh` 通过 + `./scripts/check_docs.py` 通过
4. 按 `GIT_COMMIT_CONVENTION.md` 提交；一个 commit 只做一件事。改了 `backend/app` 或
   `frontend/src` 的那次提交必须**紧跟一次状态文档提交**，否则 `check_docs.py` 会判定进度落后并拦下后续提交

## 硬约束（不可违反）

1. 需求基线只有 `IQE-Agent-Platform-Demo开发指导文档_v2.md`；`docs/archive/` 一律不作依据。
2. **万物插件**：新能力先加插件类（`backend/app/plugins/`），不在 `main.py` 或 service 里内联业务分支。
3. 事件信封逐字对齐文档 3.1；`EventEnvelope` 是 `extra="forbid"`，**不得加字段**（6 个 `event_type`、5 个 `status` 固定）。
4. **不修改任何设备密码或外部平台配置**（Airflow / 飞书 / Qoder CN 后台同理，只读）。
5. 后端只绑 `127.0.0.1`，不开放公网、不引入登录体系（可选 Bearer Token 除外）。
6. 真实外部依赖不可用时必须降级到 Mock，并把降级原因写进 Trace / `fallback_reason`，不得静默吞掉。
7. 密钥只能来自插件 `config_schema`；响应、日志、演示数据中一律脱敏，禁止写进仓库。
8. `config.py` 的 `DOC_BASELINES`（8/12/45 分钟等）来自文档场景 5/1，**数值不得改写**；模拟耗时须标注来源。
9. Prompt 优先级为 阶段 > 插件 > 默认，且每次事件必须记录 `prompt_version/prompt_source/prompt_hash`。
10. **WIP=1**：一次只做一个 FEATURES.md 任务；做 A 时不"顺便"重构 B。
11. 未通过第 1-3 层验证，不得把任务标为完成；状态由验证脚本更新，不手改勾选。
12. 测试与冒烟一律用 `IQE_DB_PATH` 指向临时库，**不得污染** `backend/data/iqe_demo.db`。
13. 文档未定义的参数 / 契约一律先在 `docs/待确认问题清单.md` 登记 Q 编号并给出推荐方案，再落代码。
14. `backend/requirements.txt` 用等号锁版本；前端保留 `package-lock.json`。
15. 会话结束必须留干净状态：验证通过、进度已记录、无临时文件与未记录半成品。

## 文档索引（按需展开）

| 文档 | 什么时候读 |
|---|---|
| `PROGRESS.md` | 每次会话开始 — 当前状态、阻塞项、下一步 |
| `FEATURES.md` | 选任务时 — 每个任务的验收标准、依赖、关联 commit |
| `STARTUP_READINESS.md` | 环境跑不起来、或要改启动流程时 |
| `GIT_COMMIT_CONVENTION.md` | 提交前 — type/scope 表、消息模板、检查点策略 |
| `IQE-Agent-Platform-Demo开发指导文档_v2.md` | 查需求、验收标准、插件契约原文（v2.5，唯一基线） |
| `docs/产品设计说明.md` | 改架构、改事件信封、改插件隔离时 |
| `docs/待确认问题清单.md` | 遇到文档没定义的行为时（F/G/H 节是已确认基线） |
| `docs/操作指南.md` | 需要手工跑 5 个演示场景、或对接真实 Airflow/飞书时 |
| `README.md` | 面向使用者：启动、可选环境变量、飞书通知配置项 |
| `scripts/*.sh` + `scripts/*.py` | 改启动 / 验证 / 冒烟 / 文档检查逻辑时 |
