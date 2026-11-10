# IQE-Agent Platform Demo 功能清单与任务分解

> **总任务数**: 24（Task 1-22 产品功能 + Task 23-24 Harness 补齐）  
> **已完成**: 14 (58%) — 逐条统计 `### Task` 标题的 ✅ 标记  
> **验收命令**: `./scripts/verify.sh`（三层：静态 → 单元/集成 → 真实进程冒烟）+ `backend/.venv/bin/python scripts/check_docs.py`  
> **最后更新**: 2026-11-10
>
> 修正记录：原头部写「总任务数 28 / 已完成 22 (79%)」，与正文实际条目（22 个 Task、13 个 ✅）不符，
> 属第 8-9 讲描述的手改状态失真；头部数字现按正文重算。

---

## 元信息

| 指标 | 值 |
|---|---|
| 后端测试覆盖 | 57/57 passed |
| 静态检查 | ruff（backend + scripts）+ mypy（41 模块，16 个模块带豁免）+ eslint + tsc |
| 运行时冒烟 | `scripts/smoke_test.py`：场景 1 + 场景 2，真实进程、临时库 |
| 前端页面数 | 8 个 |
| 插件类型 | 8 类 (输入源 / Agent / 知识库 / 工具 / 编排 / LLM / 事件总线 / 存储) |
| 演示场景 | 5 个 |
| Git commits | 见 `git log --oneline`（init checkpoint 之后新增 harness 补齐提交） |

---

## 阶段一：Init 基础设施 (已完成 ✅)

### Task 1: 项目脚手架搭建 ✅
**描述**: 建立前后端分离的项目结构，配置开发环境  
**验收标准**:
- [x] `backend/` 目录包含 FastAPI 应用，`uvicorn` 可启动 (:8000)
- [x] `frontend/` 目录包含 React + TypeScript + Vite 应用，`npm run dev` 可启动 (:3200)
- [x] `scripts/run_backend.sh` 和 `scripts/run_frontend.sh` 一键启动脚本可用
- [x] `.gitignore` 排除 `node_modules/`、`.venv/`、`__pycache__/`、`*.db`  
**依赖**: 无  
**关联 commit**: `eedc0d4`

---

### Task 2: 8 类插件框架实现 ✅
**描述**: 按"万物插件"原则，实现 8 类插件的注册、加载、健康检查机制  
**验收标准**:
- [x] `backend/app/plugins/registry.py` 插件注册中心可用
- [x] `backend/app/plugins/base.py` 定义统一插件接口 (`plugin_id` / `display_name` / `config_schema` / `health()`)
- [x] 8 类插件均可独立加载：输入源 / Agent / 知识库 / 工具 / 编排引擎 / LLM 提供商 / 事件总线 / 存储
- [x] 插件配置页面可展示/修改 `config_schema`，密钥字段脱敏显示  
**依赖**: Task 1  
**关联 commit**: `eedc0d4`

---

### Task 3: 标准事件信封定义 ✅
**描述**: 按文档 3.1 定义 Pydantic v2 强校验的事件模型  
**验收标准**:
- [x] `backend/app/models/event.py` 包含 `EventEnvelope` 模型
- [x] 字段完整：`event_id` / `event_type` (6 值) / `source_agent` / `timestamp` / `trace_id` / `confidence` (0.0-1.0) / `status` (5 值) / `model_info` / `payload`
- [x] `test_event_schema.py` 6 项测试全部通过
- [x] 额外字段自动拒绝，类型错误抛出 `ValidationError`  
**依赖**: Task 1  
**关联 commit**: `eedc0d4`

---

### Task 4: 6 个 Agent 实现 ✅
**描述**: 按文档 4.2 流水线模板实现 6 个串行 Agent  
**验收标准**:
- [x] `monitor_agent` — 接收 `monitor_alert`，归一化/去噪
- [x] `triage_agent` — 分类 + 置信度评估 + 知识库检索
- [x] `reproduction_agent` — 复现步骤生成
- [x] `ticket_agent` — 工单草稿生成
- [x] `reviewer_agent` — 置信度判定 (< 0.7 转人工，≥ 0.7 自动通过)
- [x] `reporting_agent` — 生成最终报告
- [x] `test_agents.py` 18 项测试全部通过  
**依赖**: Task 2, Task 3  
**关联 commit**: `eedc0d4`

---

### Task 5: Mock 降级矩阵实现 ✅
**描述**: 按文档 7.4 实现插件级自动降级  
**验收标准**:
- [x] Airflow 不可用 → 自动切换到内存编排器
- [x] Qoder CN 不可用/未配置 → 自动切换到 Mock LLM
- [x] Mock Jenkins / Mock Jira 作为默认演示插件
- [x] 降级原因记录在 Trace 的 `model_info.loc` 字段 (`mock` / `local_strix_halo` / `cloud_qoder_cn`)  
**依赖**: Task 2  
**关联 commit**: `eedc0d4`

---

### Task 6: 57 项自动化测试 ✅
**描述**: 覆盖 API / Agent / 插件 / 安全 / 事件 schema 的完整测试套件  
**验收标准**:
- [x] `test_api_flow.py` — 12 项 API 端到端测试
- [x] `test_agents.py` — 18 项 Agent 单元测试
- [x] `test_input_sources.py` — 8 项输入源测试
- [x] `test_event_schema.py` — 6 项事件 schema 校验
- [x] `test_security.py` — 5 项安全测试 (密钥脱敏 + Bearer Token)
- [x] `test_feishu_notifier.py` — 4 项飞书通知测试
- [x] `test_runtime.py` — 4 项运行时隔离测试
- [x] `./scripts/verify.sh` 一键验收脚本可用  
**依赖**: Task 1-5  
**关联 commit**: `eedc0d4`

---

## 阶段二：生产化扩展 (已完成 ✅)

### Task 7: Airflow 输入源插件 ✅
**描述**: 按 Q24 将 Airflow 从编排器改为输入源插件，实现真实轮询  
**验收标准**:
- [x] `backend/app/plugins/airflow_input.py` 实现 REST v2 + JWT (Airflow 3) / v1 + Basic (Airflow 2) 自动探测
- [x] `dag_ids` 配置：留空 = 监控全部 DAG，非空 = 仅监控指定 DAG
- [x] 以 `dag_id:dag_run_id` 幂等去重，避免重复触发
- [x] 失败 Run 自动转换为 `monitor_alert` 事件并触发流水线
- [x] 真实 Airflow 3.3.1 已验证 (端口 18080)  
**依赖**: Task 2, Task 3  
**关联 commit**: `66d9088`

---

### Task 8: 外部日志文件输入源 ✅
**描述**: 按 Q24 新增 `file_input` 插件，支持监控本地日志文件  
**验收标准**:
- [x] `backend/app/plugins/file_input.py` 实现日志文件轮询
- [x] 支持配置多个日志文件路径
- [x] 检测到新日志行时自动触发 `monitor_alert`
- [x] `test_input_sources.py` 相关测试通过  
**依赖**: Task 2, Task 3  
**关联 commit**: `66d9088`

---

### Task 9: 画布自定义功能 ✅
**描述**: 按 Q20/Q24 扩展画布编辑能力  
**验收标准**:
- [x] 可新增/删除输入源节点
- [x] 可新增/删除 Agent 节点，允许重复 Agent
- [x] 阶段序号可拖拽排序，保存后下一次 Run 生效
- [x] 每个阶段可编辑 Prompt / LLM / 知识库 / 工具 / 卡点配置
- [x] 旧流水线定义读取时自动迁移到新 schema  
**依赖**: Task 2, Task 4  
**关联 commit**: `66d9088`

---

### Task 10: Qoder CN 真实 LLM 接入 ✅
**描述**: 按 Q9 实现 OpenAI 兼容接口的真实 LLM 插件  
**验收标准**:
- [x] `backend/app/plugins/qoder_cn_llm.py` 实现 `POST /v1/chat/completions` 调用
- [x] `GET /v1/models` 健康检查接口可用
- [x] 支持 ` ```json ` 代码围栏与说明文字包裹的 JSON 提取
- [x] 无凭据/不可用时自动降级到 Mock LLM，Trace 标注降级原因
- [x] 真实代理 (DeepSeek-Flash via :3000) 已验证  
**依赖**: Task 2  
**关联 commit**: `66d9088`

---

### Task 11: 飞书通知插件 ✅
**描述**: 按 Q26 实现流水线结束后的通知能力  
**验收标准**:
- [x] `backend/app/plugins/feishu_notifier.py` 实现 Webhook + 应用双模式
- [x] Webhook 模式：群自定义机器人，配置 `webhook_url`
- [x] 应用模式：配置 `app_id` / `app_secret` / `receive_id_type` / `receive_id`
- [x] 按 Run + 状态幂等，同一 Run 的同一状态只发送一次
- [x] 失败隔离，重试记录在 `run_notifications` 表
- [x] 卡片内容包含状态/案例/分类/置信度/工单号/TAT/Trace 按钮  
**依赖**: Task 2, Task 6  
**关联 commit**: `66d9088`

---

### Task 12: Prompt 可配置机制 ✅
**描述**: 按文档要求实现 6 个 Agent 的 Prompt 插件化配置  
**验收标准**:
- [x] `backend/app/plugins/agents/prompts.py` 定义默认 System Prompt
- [x] 插件配置页可修改 Prompt，优先级：阶段 > 插件 > 默认
- [x] Trace 记录 `prompt_version` / `prompt_source` / `prompt_hash`
- [x] Mock LLM 不依赖 Prompt 内容，真实 LLM 使用配置的 Prompt  
**依赖**: Task 4, Task 10  
**关联 commit**: `66d9088`

---

## 阶段三：演示场景验证 (进行中 🔄)

### Task 13: 场景 1 端到端自动化验证 🔄
**描述**: 验证数据源 → 场景 1 的完整流程  
**验收标准**:
- [x] 6 个 Agent 自动流转，无人工干预 — `scripts/smoke_test.py` 层 3 断言完整事件序列
- [x] 创建 Mock Jira 工单 — 冒烟断言工单 key 前缀 `IQE-`
- [ ] TAT 约 8 分钟 (模拟值，标注"文档基线") — 属面板展示，需人工点验
- [ ] Trace 页面可查看完整事件链路 — 属 UI，需浏览器点验  
**依赖**: Task 1-12  
**当前进度**: 75% — 真实进程 + API 层已由 `test_scene_1_end_to_end_and_envelope` 与层 3 冒烟覆盖，剩两项是界面展示  
**卡点**: 无

---

### Task 14: 场景 2 人工卡点验证 🔄
**描述**: 验证低置信度时的人工审批流程  
**验收标准**:
- [x] 构造置信度 0.6 < 0.7 的案例 — `IQE-CASE-019`
- [x] Reviewer 暂停，状态变为 `waiting_human`
- [x] 可驳回或批准，驳回时记录原因 — 驳回路径断言 `ticket is None`；批准路径由层 3 冒烟断言 `reviewed_by=human`
- [ ] 飞书通知 (如配置) 发送审批请求 — 需真实凭据，未配置时按 Task 11 的幂等/失败隔离测试覆盖  
**依赖**: Task 11, Task 13  
**当前进度**: 90% — 卡点与两条决策路径均有自动化验证，剩真实飞书投递需人工配置

---

### Task 15: 场景 3 知识库加速验证 🔄
**描述**: 验证知识库命中后置信度提升 + 耗时缩短  
**验收标准**:
- [x] 知识库入库接口 — Reviewer 阶段自动保存案例摘要 + Triage 结论
- [x] 知识库检索接口 — 词频余弦相似度，TopK=3，阈值=0.35
- [x] **案例 A**: Triage 置信度 0.75，未命中知识库
- [x] **案例 B**: Triage 置信度 0.92，命中案例 A 的知识，耗时 30s (vs 3min)
- [ ] 真实 Qoder CN LLM 路径下的同等结论（当前数值由 Mock LLM 按检索命中驱动）  
**依赖**: Task 4, Task 13  
**当前进度**: 90% — `test_scene_3_knowledge_boost` 端到端通过（`IQE-CASE-017` → 入库 → `IQE-CASE-018`：0.75/180000ms → 0.92/30000ms，`kb_hit=true`）  
**卡点**: 原记"案例 B query 构造不一致导致未命中"经复核不成立，已撤销；剩余缺口是真实 LLM 路径（见 PROGRESS.md I1）

---

### Task 16: 场景 4 平台独立性验证 ⏳
**描述**: 验证 Airflow / Qoder CN 不可用时的降级能力  
**验收标准**:
- [ ] 禁用 Airflow 插件，流水线使用内存编排器正常运行
- [ ] 禁用 Qoder CN 凭据，LLM 自动降级到 Mock
- [ ] 插件管理页面展示降级原因
- [ ] Trace 中 `model_info.loc` 标注 `mock`  
**依赖**: Task 7, Task 10  
**当前进度**: 0% — 未开始

---

### Task 17: 场景 5 成本对比验证 ⏳
**描述**: 验证实验面板的云端/本地/人工对比数据  
**验收标准**:
- [ ] 实验面板展示文档基线：云端 8min / 本地 12min / 人工 45min
- [ ] 明确标注"文档基线 / 模拟指标"来源
- [ ] 对比图表可读，TAT / 成本 / 置信度三维度展示  
**依赖**: Task 13-16  
**当前进度**: 0% — 未开始

---

## 阶段四：收尾与交付 (待开始 ⏳)

### Task 18: 5 个场景完整验收录屏 ⏳
**描述**: 跑通所有演示场景，记录 Trace ID 和截图  
**验收标准**:
- [ ] 每个场景至少跑 3 次，确认稳定性
- [ ] 截图包含：仪表盘 / 画布 / Trace 详情 / 实验面板
- [ ] 整理成 `docs/验收报告.md`  
**依赖**: Task 13-17

---

### Task 19: 实验面板 TAT 来源标注优化 ⏳
**描述**: 按 I3 问题修复实验面板的标注逻辑  
**验收标准**:
- [ ] 对比图表中明确区分"文档基线" / "模拟指标" / "实测值"
- [ ] 鼠标悬停时显示数据来源说明  
**依赖**: Task 17

---

### Task 20: 代码清理与文档补全 ⏳
**描述**: 清理临时文件，补全 README 和操作指南  
**验收标准**:
- [ ] 删除 `backend/app/plugins/__pycache__/` 和所有 `.pyc`
- [ ] `README.md` 包含快速启动 / 5 个场景 / 测试命令
- [ ] `docs/操作指南.md` 包含每个场景的详细步骤  
**依赖**: Task 18

---

### Task 21: 安全边界审查 ⏳
**描述**: 按文档 0.4 / Q13 审查安全相关实现  
**验收标准**:
- [ ] 后端绑定 `127.0.0.1`，不对外暴露
- [ ] 插件密钥在响应和日志中脱敏为 `***`
- [ ] 可选 Bearer Token (`IQE_API_TOKEN`) 功能可用
- [ ] 不修改任何设备密码或外部平台配置  
**依赖**: Task 2-12

---

### Task 22: 初始化检查点提交 ✅
**描述**: 按第 6 讲要求，提交干净的 init checkpoint  
**验收标准**:
- [x] `PROGRESS.md` 创建并记录当前状态
- [x] `FEATURES.md` 创建并分解 28 个任务
- [x] `./scripts/verify.sh` 通过 (57 tests + build)
- [x] Git commit: `chore: add PROGRESS.md and FEATURES.md as init checkpoint`  
**依赖**: Task 1-21  
**关联 commit**: `1a6c0ce`（原标"待提交"，四个状态文件已于 2026-11-10 入库）

---

## 阶段五：Harness 补齐 (进行中 🔄)

### Task 23: Harness P0 四项落地 ✅
**描述**: 按 harness 审计结论补齐指令层与反馈层缺口：状态文件入库、AGENTS.md 入口、三层终止检查、CI 与 pre-commit  
**验收标准**:
- [x] 四个状态文件（PROGRESS / FEATURES / GIT_COMMIT_CONVENTION / STARTUP_READINESS）已 git 跟踪
- [x] `AGENTS.md` 存在且 ≤100 行，含首次运行 / ≤15 条硬约束 / 文档索引 / 会话上下班例程
- [x] v1 需求文档移入 `docs/archive/`，根目录不再有两份矛盾基线
- [x] `./scripts/verify.sh` 三层逐层 gating，第 1 层失败即不跑第 2、3 层（已用故意违规探针反向验证）
- [x] 第 1 层静态检查真实全绿：ruff（backend+scripts）、mypy、eslint、tsc
- [x] 第 3 层 `scripts/smoke_test.py` 起真实进程跑通场景 1 + 场景 2，并断言 0 失败 Run / 0 死信 / Demo 库未被改动
- [x] `.github/workflows/check.yml` 与 `scripts/check_docs.py` 存在，pre-commit 已安装且未覆盖 Qoder hooks
**依赖**: Task 1-22  
**关联 commit**: `0a677fc`（AGENTS.md + v1 归档）、`bef9e91`（静态工具链 + 代码修复）、`8705a70`（状态文档）、`44aa943`（三层门禁 + 冒烟 + 文档检查 + CI/pre-commit）  
**维护约定**: 头部"总任务数 / 已完成"必须跟着 `### Task` 条目与实际勾选重算。`check_docs.py` 只校验链接/入库/新鲜度，不校验计数，所以这项靠收工例程人工核对——本次已重算为 24 / 14

---

### Task 24: mypy 渐进豁免收口 ⏳
**描述**: 取消 `backend/mypy.ini` 里 16 个模块的豁免，让类型层覆盖全树（见 PROGRESS.md 已知问题 I4）  
**根因**: `BasePlugin.dependencies` 同名两用（ClassVar 声明依赖插件 id vs 实例属性装注入对象），且插件能力是 duck-typing：
`build_alert` 只在 `mock_jenkins`、`create_ticket` 只在 `jira_mock`、`list_entries/add/search` 只在 `memory_vector_kb`；
`AgentPlugin.run` 基类返回 `dict`，六个 Agent 实际返回 `EventEnvelope`。  
**验收标准**:
- [ ] 用能力 Protocol 或类型化访问器替代 `registry.get(...) -> BasePlugin` 后的 attr-defined（内核仍不得 import 具体插件类）
- [ ] 放宽 `AgentPlugin.run` 基类返回类型，消除 8 处 override
- [ ] 删除或修正无人调用的 `BasePlugin.describe()`（它把实例依赖字典当 API 字段返回，一旦被用会序列化插件对象）
- [ ] `backend/mypy.ini` 的 `disable_error_code` 段落清空，`mypy app` 全绿
- [ ] 过程中新增的 union-attr / arg-type / index / assignment 逐条按真实修因而非加豁免  
**依赖**: Task 23  
**当前进度**: 0% — 未开始

---

## 任务依赖关系图

```
Task 1 (脚手架)
  ├─→ Task 2 (插件框架)
  │     ├─→ Task 3 (事件信封)
  │     │     └─→ Task 4 (6 Agent)
  │     │           └─→ Task 12 (Prompt 配置)
  │     ├─→ Task 5 (Mock 降级)
  │     ├─→ Task 7 (Airflow 输入源)
  │     ├─→ Task 8 (文件输入源)
  │     ├─→ Task 10 (Qoder CN LLM)
  │     └─→ Task 11 (飞书通知)
  └─→ Task 6 (57 测试)
        └─→ Task 9 (画布自定义)
              └─→ Task 13-17 (5 场景验证)
                    └─→ Task 18-21 (收尾交付)
                          └─→ Task 22 (初始化检查点)
                                └─→ Task 23 (Harness P0 补齐)
                                      └─→ Task 24 (mypy 豁免收口)
```

---

## 验收命令速查

```bash
# 三层终止检查（静态 → 单元/集成 → 真实进程冒烟）
./scripts/verify.sh

# 层 1 单独跑
backend/.venv/bin/ruff check backend scripts
(cd backend && .venv/bin/mypy app)
(cd frontend && npm run lint && npm run typecheck)

# 层 2 单独跑
(cd backend && .venv/bin/pytest -q)
(cd frontend && npm run build)

# 层 3 单独跑（临时库 + 随机端口，不碰 Demo 库，可反复执行）
backend/.venv/bin/python scripts/smoke_test.py

# 文档健康检查
backend/.venv/bin/python scripts/check_docs.py

# 静态工具安装（新克隆后需要先跑一次）
uv pip install -p backend/.venv/bin/python -r backend/requirements-dev.txt
backend/.venv/bin/pre-commit install

# 启动服务
./scripts/run_backend.sh  # :8000
./scripts/run_frontend.sh # :3200

# 重置演示数据
./scripts/reset_demo.sh --yes
```
