# IQE-Agent Platform Demo 启动就绪清单

> **文档版本**: v1.1  
> **创建时间**: 2026-11-05  
> **依据**: [lecture-06](file:///home/amd/LAI-D/learn-harness-engineering/docs/zh/lectures/lecture-06-why-initialization-needs-its-own-phase/index.md) "启动就绪清单的四个条件"  
> **最后验证**: 2026-11-10 — ✅ 三层验收全绿 (9s)

---

## 启动就绪四条件

按第 6 讲定义，项目必须同时满足以下四点，才算初始化完成：

| # | 条件 | 状态 | 验证方式 |
|---|---|---|---|
| 1 | **能启动** | ✅ 通过 | `./scripts/run_backend.sh` + `./scripts/run_frontend.sh` |
| 2 | **能测试** | ✅ 通过 | `./scripts/verify.sh` — 三层 gating：静态 (ruff/mypy/eslint/tsc) → 测试 (57 pytest + vite build) → 真实进程冒烟 |
| 3 | **能看进度** | ✅ 通过 | `AGENTS.md` + `PROGRESS.md` + `FEATURES.md` 存在且内容完整，并由 `scripts/check_docs.py` 校验一致性 |
| 4 | **能接手下一步** | ✅ 通过 | 新会话只看本仓库即可回答"怎么跑""怎么测""做到哪了"，入口是 `AGENTS.md` |

---

## 一、启动命令

### 1.1 一键启动

```bash
# 后端 (端口 8000)
./scripts/run_backend.sh

# 前端 (端口 3200)
./scripts/run_frontend.sh
```

### 1.2 手动启动

```bash
# 后端
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
# 跑 verify.sh 还需要静态检查工具链（run_backend.sh 本身不需要）
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端
cd frontend
npm install
npm run dev -- --port 3200
```

### 1.3 验证命令

```bash
# 三层终止检查：层 1 静态 → 层 2 测试/构建 → 层 3 真实进程冒烟，逐层 gating
./scripts/verify.sh

# 层 1 单独跑
backend/.venv/bin/ruff check backend scripts
(cd backend && .venv/bin/mypy app)
(cd frontend && npm run lint && npm run typecheck)

# 层 2 单独跑
cd backend && .venv/bin/pytest -q          # 57 项
cd frontend && npm run build               # tsc -b + vite build

# 层 3 单独跑（起真实 uvicorn + 临时库，不污染 backend/data/iqe_demo.db）
backend/.venv/bin/python scripts/smoke_test.py

# 文档一致性（链接可达 / 状态文件已入库 / 进度未落后于代码）
backend/.venv/bin/python scripts/check_docs.py

# 检查服务是否启动
curl http://127.0.0.1:8000/docs  # 应返回 OpenAPI JSON
curl http://127.0.0.1:3200       # 应返回 HTML
```

### 1.4 辅助命令

```bash
# 重置演示数据 (清除 SQLite 数据库)
./scripts/reset_demo.sh --yes

# 提交时自动跑三层验收 + 文档检查（只写 .git/hooks/pre-commit，不动 Qoder tracker 的其它钩子）
backend/.venv/bin/pre-commit install
backend/.venv/bin/pre-commit uninstall

# 查看 Git 提交历史
git log --oneline

# 查看当前进度
head -30 AGENTS.md PROGRESS.md
```

---

## 二、当前状态

### 2.1 依赖状态

| 依赖 | 版本 | 状态 |
|---|---|---|
| Python | 3.12 | ✅ 已安装，虚拟环境 `.venv/` 已创建 |
| Node.js | 22+ | ✅ 已安装 |
| uv | latest | ✅ 已安装 (Python 包管理) |
| npm | 10+ | ✅ 已安装 |
| FastAPI | 0.162.0 | ✅ 已锁定在 `requirements.txt` |
| Pydantic | 2.14.2 | ✅ 已锁定 |
| ruff | 0.14.6 | ✅ 已锁定在 `requirements-dev.txt` |
| mypy | 1.19.0 | ✅ 已锁定，配置见 `backend/mypy.ini` |
| pre-commit | 4.7.0 | ✅ 已锁定，钩子已安装到 `.git/hooks/pre-commit` |
| React | 18 | ✅ 已锁定在 `package-lock.json` |
| TypeScript | ^5.8.0 (实装 5.9.3) | ✅ 锁定在 `package-lock.json` |
| ESLint | 9.39.5 (flat config) | ✅ 配置见 `frontend/eslint.config.js` |
| Vite | 6.4.5 | ✅ 已锁定 |

### 2.2 测试状态

```bash
$ ./scripts/verify.sh
==> 层 1/3 静态检查 :: ruff (backend + scripts)
All checks passed!
==> 层 1/3 静态检查 :: backend mypy
Success: no issues found in 41 source files
==> 层 1/3 静态检查 :: frontend eslint
0 errors, 1 warning
==> 层 1/3 静态检查 :: frontend tsc
==> 层 2/3 单元与集成 :: backend pytest
57 passed, 1 warning in 1.53s
==> 层 2/3 前端构建 :: tsc + vite build
✓ 794 modules transformed.
✓ built in 1.95s
==> 层 3/3 运行时冒烟 :: 真实进程端到端
SMOKE OK  真实进程跑通场景 1 / 场景 2
VERIFY OK  三层全部通过，用时 9s
```

第 3 层用真实 uvicorn 子进程 + `IQE_DB_PATH` 临时库，断言事件序列、人工卡点批准后 `reviewed_by=human`、0 失败 Run、0 死信，并校验 `backend/data/iqe_demo.db` 未被写入。

| 测试套件 | 通过 | 失败 | 备注 |
|---|---|---|---|
| `test_api_flow.py` | 12 | 0 | ✅ API 端到端流程 |
| `test_agents.py` | 18 | 0 | ✅ 6 个 Agent 单元测试 |
| `test_input_sources.py` | 8 | 0 | ✅ Airflow / Mock Jenkins / 文件输入源 |
| `test_event_schema.py` | 6 | 0 | ✅ 事件信封 Pydantic 校验 |
| `test_security.py` | 5 | 0 | ✅ 密钥脱敏 + Bearer Token |
| `test_feishu_notifier.py` | 4 | 0 | ✅ 飞书通知幂等 + 失败隔离 |
| `test_runtime.py` | 4 | 0 | ✅ 插件隔离 + 超时控制 |
| **合计** | **57** | **0** | ✅ **全部通过** |

### 2.3 服务状态

| 服务 | 端口 | 状态 | 访问地址 |
|---|---|---|---|
| 后端 API | 8000 | ✅ 可启动 | http://127.0.0.1:8000 |
| OpenAPI 文档 | 8000 | ✅ 自动生成 | http://127.0.0.1:8000/docs |
| 前端开发服务器 | 3200 | ✅ 可启动 | http://127.0.0.1:3200 |
| Airflow (可选) | 18080 | ⚠️ 需手动启动 | http://127.0.0.1:18080 |

### 2.4 集成状态

| 外部系统 | 集成方式 | 状态 |
|---|---|---|
| Airflow | 输入源插件 (REST v2 + JWT / v1 + Basic) | ✅ 真实轮询已验证 |
| Qoder CN LLM | OpenAI 兼容接口 (DeepSeek-Flash via :3000) | ✅ 真实代理已接入 |
| 飞书通知 | Webhook + 应用双模式 | ✅ 已实现，需用户配置凭据 |
| Mock Jenkins | 内置演示插件 | ✅ 默认可用 |
| Mock Jira | 内置演示插件 | ✅ 默认可用 |

---

## 三、项目结构

```
AI_Agent_Pipeline/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口与 API
│   │   ├── models/
│   │   │   └── event.py            # 文档 3.1 标准事件信封
│   │   ├── plugins/                # 8 类插件 + 6 个 Agent
│   │   │   ├── airflow_input.py    # Airflow 输入源 (REST v2/v1)
│   │   │   ├── file_input.py       # 外部日志文件输入源
│   │   │   ├── feishu_notifier.py  # 飞书通知插件
│   │   │   ├── qoder_cn_llm.py    # Qoder CN LLM 插件
│   │   │   ├── mock_jenkins.py     # Mock Jenkins
│   │   │   ├── mock_jira.py        # Mock Jira
│   │   │   ├── mock_llm.py         # Mock LLM
│   │   │   ├── memory_orchestrator.py  # 内存编排器
│   │   │   ├── memory_vector_kb.py     # 内存向量知识库
│   │   │   ├── memory_event_bus.py     # 内存事件总线
│   │   │   ├── sqlite_storage.py       # SQLite 存储
│   │   │   ├── agents/                 # 6 个 Agent 实现
│   │   │   │   ├── monitor_agent.py
│   │   │   │   ├── triage_agent.py
│   │   │   │   ├── reproduction_agent.py
│   │   │   │   ├── ticket_agent.py
│   │   │   │   ├── reviewer_agent.py
│   │   │   │   ├── reporting_agent.py
│   │   │   │   └── prompts.py          # 默认 System Prompt
│   │   │   ├── base.py             # 插件基类
│   │   │   └── registry.py         # 插件注册中心
│   │   ├── services/               # 编排、通知、降级、审批、知识库
│   │   ├── config.py               # 配置管理
│   │   ├── db.py                   # SQLite 持久化
│   │   ├── seed.py                 # 文档 4.2 流水线模板
│   │   ├── security.py             # 安全 / 脱敏
│   │   ├── errors.py               # 错误处理
│   │   └── logging_config.py       # 日志配置
│   ├── tests/                      # 57 项自动化测试
│   ├── data/                       # SQLite 数据库文件 (运行时生成)
│   ├── mypy.ini                    # 层 1 类型检查（渐进豁免清单）
│   ├── requirements.txt            # Python 运行时依赖
│   ├── requirements-dev.txt        # ruff / mypy / pre-commit
│   └── .venv/                      # Python 虚拟环境
├── frontend/
│   ├── src/
│   │   ├── pages/                  # 8 个演示页面
│   │   │   ├── CanvasPage.tsx      # 画布自定义
│   │   │   ├── DashboardPage.tsx   # 仪表盘
│   │   │   ├── DataSourcesPage.tsx # 数据源管理
│   │   │   ├── ExperimentsPage.tsx # 实验面板
│   │   │   ├── KnowledgePage.tsx   # 知识库管理
│   │   │   ├── PluginsPage.tsx     # 插件管理
│   │   │   ├── TracesPage.tsx      # Trace 列表
│   │   │   └── TraceDetailPage.tsx # Trace 详情
│   │   ├── components/             # React 组件
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json                # Node 依赖 + lint/typecheck 脚本
│   ├── eslint.config.js            # 层 1 前端 lint（flat config）
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── node_modules/
├── docs/
│   ├── archive/                    # 已废弃基线（v1 需求文档），不作实现依据
│   ├── 产品设计说明.md
│   ├── 操作指南.md
│   └── 待确认问题清单.md
├── .github/workflows/
│   └── check.yml                   # CI：跑 verify.sh 三层 + check_docs.py
├── scripts/
│   ├── run_backend.sh              # 一键启动后端
│   ├── run_frontend.sh             # 一键启动前端
│   ├── verify.sh                   # 三层终止检查（层间 gating）
│   ├── smoke_test.py               # 层 3：真实进程端到端冒烟
│   ├── check_docs.py               # 文档链接 / 状态文件 / 陈旧度检查
│   └── reset_demo.sh               # 重置演示数据
├── AGENTS.md                       # agent 入口路由器（先读这个）
├── PROGRESS.md                     # 进度日志
├── FEATURES.md                     # 功能清单与任务分解
├── STARTUP_READINESS.md            # 启动就绪清单 (本文件)
├── GIT_COMMIT_CONVENTION.md        # Git 提交规范
├── README.md                       # 项目说明
├── IQE-Agent-Platform-Demo开发指导文档_v2.md  # 产品需求文档（唯一基线）
├── ruff.toml                       # 层 1 Python lint（仓库根，覆盖 backend + scripts）
├── .pre-commit-config.yaml         # 提交时跑三层验收 + 文档检查
└── .git/                           # Git 仓库
```

---

## 四、任务分解

详见 [FEATURES.md](FEATURES.md)，共 24 个任务（Task 1-22 产品功能 + Task 23-24 Harness 补齐），分为 5 个阶段：

| 阶段 | 任务数 | 已完成 | 进度 |
|---|---|---|---|
| 阶段一：Init 基础设施 | 6 | 6 | ✅ 100% |
| 阶段二：生产化扩展 | 6 | 6 | ✅ 100% |
| 阶段三：演示场景验证 | 5 | 0 | 🔄 Task 13 75% / Task 14 90% / Task 15 90% |
| 阶段四：收尾与交付 | 5 | 1 | 🔄 仅 Task 22 完成 |
| 阶段五：Harness 补齐 | 2 | 1 | 🔄 Task 23 ✅ / Task 24 待开始 |
| **合计** | **24** | **14** | **58%** |

> 2026-11-10 修正：原表写"28 个任务 / 22 已完成 / 79%"，与实际条目不符（阶段四从未有 5 项完成，Task 23-24 也未计入）。计数以 FEATURES.md 的 `### Task` 条目为准。

### 当前优先级最高的 3 个任务

1. **[P0] Task 15: 场景 3 知识库加速验证（收尾）**
   - 当前进度: 90%
   - 已验证: Mock LLM 路径下 0.75 → 0.92、耗时 180s → 30s、`kb_hit=true`，由 `test_scene_3_knowledge_boost` 覆盖
   - 下一步: 让同一对案例走真实 Qoder CN LLM，并在 Trace 里标出数值来源
   - 原"query 构造不一致"卡点经复核不成立，已撤销

2. **[P1] Task 24: mypy 渐进豁免收口**
   - 当前进度: 0%
   - 根因: 插件能力 duck-typing 未声明在基类 + `AgentPlugin.run` 基类返回类型过窄
   - 下一步: 引入能力 Protocol，再逐模块删 `backend/mypy.ini` 的 `disable_error_code`
   - 验收标准: 16 个豁免段落清空且 `mypy app` 全绿

3. **[P2] Task 19: 实验面板 TAT 来源标注优化**
   - 当前进度: 0%
   - 问题: 管理层可能混淆"文档基线"与"实测值"
   - 下一步: 在对比图表中明确区分三种来源
   - 验收标准: 鼠标悬停显示数据来源说明

---

## 五、环境要求

### 5.1 系统要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Linux / macOS / WSL2 |
| Python | 3.12+ |
| Node.js | 22+ |
| 内存 | 4GB+ (运行 Airflow 需要 8GB+) |
| 磁盘 | 2GB+ (node_modules + .venv) |

### 5.2 网络要求

| 端口 | 用途 | 是否必需 |
|---|---|---|
| 3200 | 前端开发服务器 | ✅ 必需 |
| 8000 | 后端 API | ✅ 必需 |
| 18080 | Airflow (如启用) | ⚠️ 可选 |
| 3000 | Qoder CN 代理 (如启用) | ⚠️ 可选 |

### 5.3 外部依赖

| 依赖 | 是否必需 | 降级方案 |
|---|---|---|
| Airflow | ❌ 可选 | 自动降级到内存编排器 |
| Qoder CN LLM | ❌ 可选 | 自动降级到 Mock LLM |
| 飞书后台 | ❌ 可选 | 不配置则不发送通知 |

---

## 六、新会话接手指南

### 6.1 上班流程 (每次会话开始时)

按以下顺序读取，可在 5 分钟内恢复完整上下文：

```bash
# 1. 读 agent 入口（怎么跑 / 怎么算完成 / 硬约束）
cat AGENTS.md

# 2. 读进度日志
cat PROGRESS.md

# 3. 读功能清单，选一个 WIP=1 的任务
cat FEATURES.md | head -100

# 4. 跑三层验收，确认起点是绿的
./scripts/verify.sh

# 5. 启动服务
./scripts/run_backend.sh &
./scripts/run_frontend.sh &

# 6. 打开浏览器
# http://127.0.0.1:3200
```

> 第 4 步之前先复核 `PROGRESS.md` 的"已知问题"是否仍成立——2026-11-10 就发现 I1/I2 两条已过期（详见 `AGENTS.md` 会话开始例程第 2 条）。

> 提交顺序受门禁影响：`check_docs.py` 要求状态文档不早于代码提交，所以**改了 `backend/app` 或 `frontend/src` 的那次提交之后，必须紧跟一次状态文档提交**，否则后续每次提交都会被钩子拦下。

### 6.2 下班流程 (每次会话结束前)

```bash
# 1. 更新进度日志
vim PROGRESS.md
# - 更新"当前快照"与验证记录
# - 移动已完成任务到"已完成"部分
# - 复核并修正已知问题（过期条目标注判定依据，不直接删号）

# 2. 更新功能清单
vim FEATURES.md
# - 勾选已通过验证的 checkbox（状态由验证结果决定，不手改）
# - 更新任务进度百分比与头部计数

# 3. 跑三层验收 + 文档一致性
./scripts/verify.sh
backend/.venv/bin/python scripts/check_docs.py

# 4. 提交代码（已装 pre-commit 时会自动跑上面两步）
git status --short          # 先确认没有意外文件（密钥 / .env / 临时库）
git add <明确列出的文件>     # 不用 git add -A
git commit -m "docs(progress): update before session end

Current state: <简述当前进度>
Next: <下一步计划>

Ref: PROGRESS.md, FEATURES.md"
```

### 6.3 快速问答

**Q: 怎么跑这个项目？**  
A: 执行 `./scripts/run_backend.sh` 和 `./scripts/run_frontend.sh`，然后访问 http://127.0.0.1:3200

**Q: 怎么测试？**  
A: 执行 `./scripts/verify.sh`，逐层看到 `All checks passed!` → `57 passed` → `SMOKE OK`，最后是 `VERIFY OK 三层全部通过`；层 1 失败不会跑层 2/3

**Q: 做到哪了？**  
A: 读 `PROGRESS.md` 的"当前快照"和"进行中"部分

**Q: 下一步做什么？**  
A: 读 `PROGRESS.md` 的"下一步"部分，第一项是 P0 优先级

**Q: 卡点是什么？**  
A: 读 `PROGRESS.md` 的"已知问题"表；动手前先复核该条是否仍成立——已撤销条目保留编号并在"已澄清"里写明判定依据

**Q: 怎么验证场景 3 知识库加速？**  
A: `(cd backend && .venv/bin/pytest -q -k scene_3)`；`FEATURES.md` Task 15 列了预期数值（0.75→0.92、180s→30s）

**Q: 静态检查工具没装怎么办？**  
A: `uv pip install -p backend/.venv/bin/python -r backend/requirements-dev.txt`；`verify.sh` 的 ERROR/WHY/FIX 也会给出这条命令

---

## 七、验收清单

按第 6 讲要求，初始化阶段应产出可逐项验证的检查清单：

```markdown
## 初始化验收清单 (lecture-06 标准)

- [x] `./scripts/run_backend.sh` 从零开始能成功
- [x] `./scripts/run_frontend.sh` 从零开始能成功
- [x] `./scripts/verify.sh` 至少有一个测试通过 (实际: 三层全绿，57/57 + 冒烟)
- [x] 新的 agent 会话能只看仓库回答"怎么跑"和"怎么测"（入口 `AGENTS.md`）
- [x] 任务分解文件存在且有至少 3 个任务 (实际: 24 个)
- [x] 所有内容已提交到 git（2026-11-10 完成：状态文档 + Harness 配置全部入库，`git status` 干净）
- [x] 验收失败会告诉 agent 怎么修（`verify.sh` 输出 ERROR/WHY/FIX 三行）
- [x] 已验证门禁真的会拦截：故意加一个未用 import 的探针文件 → 层 1 退出码 1，层 2/3 未执行

## 启动就绪四条件验收

- [x] 能启动: 后端 :8000 + 前端 :3200 可一键启动
- [x] 能测试: 静态 4 项 + 57 项测试 + 前端构建 + 真实进程冒烟，逐层 gating
- [x] 能看进度: AGENTS.md + PROGRESS.md + FEATURES.md 内容完整且经 `check_docs.py` 校验
- [x] 能接手下一步: 新会话按 `AGENTS.md` 会话开始例程或本文"六、新会话接手指南"操作即可

## 额外验收 (项目特定)

- [x] 5 个演示场景的任务分解已完成
- [x] 8 类插件的目录结构清晰
- [x] 外部依赖 (Airflow / Qoder CN / 飞书) 的降级方案已文档化
- [x] 安全边界 (本机绑定 / 密钥脱敏 / 可选 Token) 已说明

## Harness 补齐验收 (2026-11-10, lecture-02/03/08/09)

- [x] 指令层入口 AGENTS.md ≤100 行，只做目录不做百科
- [x] 仓库即规范：v1 已废弃基线移入 docs/archive/，根目录只有一份基线
- [x] 三层终止检查逐层 gating，失败输出 ERROR/WHY/FIX
- [x] pass-gate：未通过验证不得标记任务完成（AGENTS.md 硬约束 11）
- [x] 状态四件套入库：AGENTS/PROGRESS/FEATURES/STARTUP_READINESS + 提交规范
- [x] CI (.github/workflows/check.yml) 与 pre-commit 使用同一套脚本，无第二套标准
```

---

## 八、参考文档

| 文档 | 路径 | 用途 |
|---|---|---|
| agent 入口 | `AGENTS.md` | 新会话第一个读的文件：怎么跑、怎么算完成、硬约束 |
| 产品需求 | `IQE-Agent-Platform-Demo开发指导文档_v2.md` | 了解产品设计和架构（唯一基线） |
| 进度日志 | `PROGRESS.md` | 了解当前状态和卡点 |
| 功能清单 | `FEATURES.md` | 了解任务分解和验收标准 |
| 提交规范 | `GIT_COMMIT_CONVENTION.md` | 了解 Git 提交标准 |
| 操作指南 | `docs/操作指南.md` | 了解 5 个演示场景的操作步骤 |
| 待确认问题 | `docs/待确认问题清单.md` | 了解已确认/待确认的决策 |
| 归档基线 | `docs/archive/` | v1 需求文档，**不作实现依据**，仅保留可追溯 |
| 静态检查配置 | `ruff.toml` / `backend/mypy.ini` / `frontend/eslint.config.js` | 层 1 规则与豁免理由 |

---

## 总结

本启动就绪清单满足第 6 讲定义的四个条件：

1. ✅ **能启动** — 一键脚本 + 手动命令 + 端口说明
2. ✅ **能测试** — 三层终止检查（静态 → 测试/构建 → 真实进程冒烟）+ CI 同一套脚本
3. ✅ **能看进度** — AGENTS.md + PROGRESS.md + FEATURES.md + 任务分解，由 `check_docs.py` 防漂移
4. ✅ **能接手下一步** — 会话开始/结束例程 + 快速问答

**项目在任何时刻都处于"可以被全新 agent 接手"的状态。**
