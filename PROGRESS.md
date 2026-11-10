# IQE-Agent Platform Demo 进度日志

> **最后更新**: 2026-11-10 (mypy 豁免收口，Task 24)  
> **当前会话目标**: 收口 mypy 16 模块豁免（Task 24，✅ 已完成并三层验证）；下一个 P0 仍是产品侧场景 3

---

## 当前快照

| 指标 | 状态 |
|---|---|
| **Harness 补齐提交** | `0a677fc` AGENTS.md 入口 → `bef9e91` 静态工具链 → `8705a70` 状态文档 → `44aa943` 三层门禁 → `4693d92` 哈希与提交顺序 → `4693d92` 哈希与提交顺序 → `2b4d7c3` mypy 豁免收口 |
| **最新 commit** | 以 `git log -1 --oneline` 为准：本字段若写死具体哈希，每次提交即自我过期，故不记录 |
| **验收命令** | ✅ `./scripts/verify.sh` 三层全绿 (ruff/mypy/eslint/tsc → pytest/build → 真实进程冒烟)，用时 ~9s |
| **后端测试** | ✅ 61/61 passed |
| **前端构建** | ✅ tsc + vite build 通过 |
| **服务状态** | 后端 :8000 / 前端 :3200 可启动 |
| **Airflow 集成** | ✅ 真实轮询已验证 (v3.3.1, 端口 18080) |
| **Qoder CN LLM** | ✅ 真实代理已接入 (DeepSeek-Flash via :3000) |
| **飞书通知** | ✅ Webhook + 应用双模式已实现 |
| **入口文档** | ✅ `AGENTS.md`（≤100 行路由器）已建立，v1 需求文档移入 `docs/archive/` |
| **静态检查债务** | ✅ mypy 0 豁免（42 文件全绿）；能力契约见 `backend/app/plugins/capabilities.py`，防复发检查见 `backend/tests/test_plugin_contracts.py` |

---

## 已完成 ✅

### Init 阶段 (2026-11-02 ~ 2026-11-03)
- [x] **项目脚手架搭建** — FastAPI + React + TypeScript + Vite (commit: `eedc0d4`)
- [x] **8 类插件框架** — 输入源 / Agent / 知识库 / 工具 / 编排 / LLM / 事件总线 / 存储
- [x] **6 个 Agent 实现** — Monitor → Triage → Reproduction → Ticket → Reviewer → Reporting
- [x] **标准事件信封** — Pydantic v2 强校验，5 个 event_type + 5 个 status
- [x] **Mock 降级矩阵** — Airflow→内存编排器 / Qoder CN→Mock LLM / Jira→Mock Jira
- [x] **57 项自动化测试** — 覆盖 API / Agent / 插件 / 安全 / 事件 schema

### 生产化扩展 (2026-11-03 ~ 2026-11-04)
- [x] **Airflow 输入源插件** — REST v2 + JWT (Airflow 3) / v1 + Basic (Airflow 2) 自动探测 (commit: `66d9088`)
- [x] **外部日志文件输入源** — `file_input.py` 支持监控本地日志文件触发流水线
- [x] **画布自定义** — 可新增/删除输入源与 Agent，允许重复，阶段排序 (Q20/Q24)
- [x] **Qoder CN 真实接入** — OpenAI 兼容接口，JSON 代码围栏解析 (Q9)
- [x] **飞书通知插件** — Webhook + 应用双模式，按 Run+状态幂等 (Q26)
- [x] **Prompt 可配置** — 6 个 Agent 默认 Prompt，支持插件级与阶段级覆盖

### Harness 补齐 (2026-11-10)
- [x] **`AGENTS.md` 指令入口** — 80 行路由器：首次运行 / 怎么算完成 / 会话例程 / 15 条硬约束 / 文档索引
- [x] **v1 需求文档归档** — `git mv` 到 `docs/archive/` + 归档说明，避免 agent 读到已废弃设定
- [x] **三层终止检查** — `scripts/verify.sh` 逐层 gating（静态 → 单元/集成 → 真实进程冒烟），失败输出 ERROR/WHY/FIX
- [x] **静态检查栈** — `ruff.toml`（仓库根，覆盖 `backend/` + `scripts/`）+ `backend/mypy.ini`（渐进豁免）+ `frontend/eslint.config.js` + `requirements-dev.txt`
- [x] **运行时冒烟** — `scripts/smoke_test.py` 起真实 uvicorn，跑场景 1 事件序列 + 场景 2 人工卡点，并断言未污染 `backend/data/iqe_demo.db`
- [x] **文档一致性检查** — `scripts/check_docs.py` 查链接可达、状态文档已入库、根目录无多版本文档、进度文档未落后于代码
- [x] **CI + pre-commit** — `.github/workflows/check.yml` 跑 verify.sh；`.pre-commit-config.yaml` 只写 `.git/hooks/pre-commit`，不影响 Qoder tracker 的其它钩子

### mypy 豁免收口 (2026-11-10，FEATURES Task 24)
- [x] **能力协议层** — 新增 `backend/app/plugins/capabilities.py`：`LLMProvider / Orchestrator / AlertSource / AlertBuilder / Ticket / Reproduce / Knowledge / Notifier / EventBus` 9 个 `runtime_checkable` Protocol + 同名 `as_*` 窄化访问器（mypy 不接受把 Protocol 传给 `type[T]`，故不用泛型访问器）
- [x] **基类契约对齐实现** — `AgentPlugin.run` 返回 `EventEnvelope`、`collect_alerts` 返回 `list[EventEnvelope]`、`start_pipeline(pipeline_def, context=None)`；8 处 override 错误清零，编排器 `context` 参数登记为 Q27
- [x] **`dependencies` 拆分** — ClassVar 依赖清单 vs 实例注入表 `resolved_dependencies`，`memory_orchestrator` 里 `runner: Any` 的就地绕过与 `describe()` 死代码一并删除
- [x] **16 个模块豁免清空** — `backend/mypy.ini` 只剩全局段；`mypy app` 42 文件 0 错误（`warn_unreachable` 开着，绿灯不是靠降级换来的）
- [x] **4 处真实缺陷顺带修掉** — kb `entry` 字面量类型、airflow `conf` 的 `None` 分支、feishu `code` 的 `int()` 兜底、`run_isolated` 的 `Awaitable`→`Coroutine`
- [x] **防复发测试** — `backend/tests/test_plugin_contracts.py`：mypy.ini 不得再出现 `disable_error_code`、内核不得 import 具体插件模块、能力窄化函数接受真插件/拒绝无能力对象（测试 57 → 61）

---

## 进行中 🔄

### 场景 3 知识库加速验证（状态文档已纠正）
- [x] 知识库入库接口 — Reviewer 阶段自动保存案例摘要 + Triage 结论
- [x] 知识库检索接口 — 词频余弦相似度，TopK=3，阈值=0.35
- [x] **原记"卡点"不成立** — `test_scene_3_knowledge_boost` 通过：案例 A `confidence=0.75 / latency_ms=180000`，入库后案例 B `confidence=0.92 / kb_hit=true / latency_ms=30000`
  - **依据**: `backend/tests/test_api_flow.py::test_scene_3_knowledge_boost`，属 57/57 通过项
  - **机制**: `mock_llm.py` 按 `kb_hits` 最高分条目驱动置信度与耗时，不是写死的返回值
- [ ] **真正未验证的**: 真实 Qoder CN LLM 路径下置信度提升是否仍成立（当前数值来自 Mock LLM 的脚本公式）
- [ ] **待补的**: 浏览器端演示脚本（画布点验 + 实验面板读数截图），本地 `smoke_test.py` 目前只覆盖场景 1/2

---

## 已知问题 ⚠️

| 编号 | 问题 | 影响 | 优先级 |
|---|---|---|---|
| I1 | 场景 3 只在 Mock LLM 下验证，真实 Qoder CN 路径未跑 | 演示时"置信度提升"依赖 Mock 公式，真实模型下数值不可预测 | P0 |
| I2 | **已撤销**：`test_pagination_edge_case` 空结果集返回 500 | 全仓搜不到该测试，`pytest -q` 57/57 全绿 | — |
| I3 | 实验面板的 TAT 来源标注不清晰 | 管理层可能混淆"文档基线"与"实测值" | P1 |
| I4 | **已收口**：mypy 16 模块 / 49 处豁免错误 → 0（FEATURES Task 24，能力 Protocol + 基类签名 + `dependencies` 拆分） | 类型绿灯现在有 `test_plugin_contracts.py` 兜住，重新加豁免会直接挂测试 | — |
| I5 | `verify.sh` 第三层冒烟只覆盖场景 1/2 | 场景 3-5 回归仍靠手工点验，agent 无法自查 | P2 |

> 编号保持稳定不复用：I2 已撤销但保留空位，因为 FEATURES.md 按编号引用 I3/I4。

### 已澄清（避免再次误判）
- **I2 不成立**：`grep -rn pagination backend/` 无匹配。教训已落到 `AGENTS.md` 的会话开始例程——状态文档里每条"已知问题"动手前先在代码里复核。
- **原 I1「场景 3 未跑通」不成立**：见上文"进行中"，该场景由 `test_scene_3_knowledge_boost` 覆盖且通过；真实缺口收窄为"仅 Mock LLM 路径"。

---

## 下一步 📋

1. **[P0]** 让场景 3 走真实 Qoder CN LLM（对应 I1）：保留 Mock 降级，把 `kb_hit → 置信度/耗时` 的取值来源在 Trace 里标成 `model_source`，演示时能说清哪部分是实测
2. **[P1]** 实验面板对比图表标注"文档基线 / 模拟指标 / 实测值"三种来源（对应 I3、FEATURES Task 19）
3. **[P2]** 把冒烟第三层扩到场景 3-5（对应 I5），使 `verify.sh` 能自证 5 个演示场景
4. **[P2]** Harness P1 项：`feature_list.json` + validator + pass-gate、`docs/` 标准目录与 `DECISIONS.md`、可执行架构规则检查

> 原「清理 `backend/app/plugins/` 下 `__pycache__` 与 `.pyc`」不成立：`.gitignore` 已忽略且 `git ls-files` 中跟踪数为 0，仓库侧无需处理。

---

## 验证记录 🧪

### 三层验收 `./scripts/verify.sh` (2026-11-10，mypy 豁免清空后，用时 9s)
```
层 1 静态    ruff check backend scripts  → All checks passed!
             mypy app (42 modules)       → Success: no issues（0 个 disable_error_code 段落）
             eslint .                    → 0 errors, 1 warning
             tsc -b                      → 通过
层 2 测试    pytest -q                   → 61 passed, 1 warning in 1.56s
             vite build                  → 794 modules，8 个页面构建成功
层 3 冒烟    smoke_test.py               → SMOKE OK 场景 1/2、0 失败 Run、0 死信、Demo 库未触碰
VERIFY OK  三层全部通过
```
这一层的绿灯不是靠豁免换来的：`backend/mypy.ini` 现在只剩全局段，`warn_unreachable = True` 仍开着；`test_plugin_contracts.py` 会在有人重新写入 `disable_error_code` 或让内核 import 具体插件模块时失败。新增 4 项测试使后端用例从 57 增至 61。

### 三层验收 `./scripts/verify.sh` (2026-11-10，Harness P0 四项落地时，用时 9s)
```
层 1 静态    ruff check backend scripts  → All checks passed!
             mypy app (41 modules)       → no issues
             eslint .                    → 0 errors, 1 warning (Toast.tsx 只导出组件)
             tsc -b                      → 通过
层 2 测试    pytest -q                   → 57 passed, 1 warning in 1.52s
             vite build                  → 8 个页面构建成功
层 3 冒烟    smoke_test.py               → SMOKE OK 真实进程跑通场景 1/2
VERIFY OK  三层全部通过
```
负向验证：临时加入含 `import os`（未使用）的 `backend/app/_verify_probe.py` 后 `verify.sh` 退出码 1，且日志中"层 2/层 3"出现 0 次——证明逐层 gating 真的在拦截，探针已删除。

### 后端测试 (2026-11-05 14:30)
```bash
cd backend && .venv/bin/pytest -q
# 57 passed, 1 warning in 1.52s
```

| 测试文件 | 通过 | 失败 | 备注 |
|---|---|---|---|
| test_api_flow.py | 12 | 0 | ✅ API 端到端流程 |
| test_agents.py | 18 | 0 | ✅ 6 个 Agent 单元测试 |
| test_input_sources.py | 8 | 0 | ✅ Airflow / Mock Jenkins / 文件输入源 |
| test_event_schema.py | 6 | 0 | ✅ 事件信封 Pydantic 校验 |
| test_security.py | 5 | 0 | ✅ 密钥脱敏 + Bearer Token |
| test_feishu_notifier.py | 4 | 0 | ✅ 飞书通知幂等 + 失败隔离 |
| test_runtime.py | 4 | 0 | ✅ 插件隔离 + 超时控制 |

### 前端构建 (2026-11-05 14:25)
```bash
cd frontend && npm run build
# tsc --noEmit && vite build
# ✅ 8 个页面编译成功
```

### 服务启动 (2026-11-05 14:35)
```bash
# 后端
cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
# ✅ INFO: Uvicorn running on http://127.0.0.1:8000

# 前端
cd frontend && npm run dev -- --port 3200
# ✅ Local: http://127.0.0.1:3200/
```

---

## 会话交接清单

新会话接手时，请按以下顺序读取（与 `AGENTS.md` 的会话开始例程一致）：

1. **读 `AGENTS.md`** — 项目是什么、怎么跑、怎么算完成、15 条硬约束
2. **读本文档** — 当前进度和阻塞项，并**逐条复核阻塞项是否仍成立**（本次就发现 I1/I2 已过期）
3. **读 `FEATURES.md`** — 选一个未完成任务，WIP=1
4. **读 `docs/待确认问题清单.md`** — 已确认/待确认的决策（F/G/H 节是基线）
5. **读 `IQE-Agent-Platform-Demo开发指导文档_v2.md`** — 需求与架构基线；`docs/archive/` 下的 v1 不作依据
6. **跑 `./scripts/verify.sh`** — 确认起点是绿的，再动手
7. **从"下一步"第 1 项开始工作** — 场景 3 走真实 LLM 路径
