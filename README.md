# IQE-Agent Platform Demo

面向管理层演示的插件化 AI Agent 编排平台,严格按 `IQE-Agent-Platform-Demo开发指导文档_v2.md`(v2.3)实现。

- **万物插件**:平台内核只做编排,输入源 / Agent / 知识库 / 工具 / 编排引擎 / LLM / 事件总线 / 存储全部可插拔。
- **端到端链路**:Monitor → Triage → Reproduction → Ticket → Reviewer → Reporting。
- **真实集成 + Mock 降级**:Airflow、Qoder CN 为可选插件,不可用时自动降级到内置编排器 / Mock LLM。
- **Prompt 可配置**:6 个 Agent 均有默认 System Prompt,支持插件级与流水线阶段级覆盖,并在 Trace 中记录版本/来源/哈希。
- **完整可观测**:每个事件符合文档 3.1 标准信封,Trace 页面可查看输入、输出、耗时、置信度、模型与降级原因。

## 5 个演示场景

| 场景 | 入口 | 预期结果 |
|---|---|---|
| 1 端到端自动化 | 数据源 → 场景 1 | 6 个 Agent 自动流转,创建 Mock Jira 工单,TAT 约 8 分钟(模拟) |
| 2 人工卡点 | 数据源 → 场景 2 | 置信度 0.6 < 0.7,Reviewer 暂停;可驳回或批准 |
| 3 知识库加速 | 数据源 → 案例 A → Trace 标记入库 → 案例 B | Triage 置信度 0.75 → 0.92,耗时 3 min → 30 s |
| 4 平台独立性 | 插件管理 / 画布 | Airflow / Qoder CN 不可用时自动降级,流水线照常运行 |
| 5 成本对比 | 实验面板 | 云端 / 本地 / 人工的 TAT、成本、置信度对比 |

详细步骤见 [docs/操作指南.md](docs/操作指南.md)。

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.12、FastAPI、Pydantic v2、asyncio、httpx、SQLite |
| 前端 | React 18、TypeScript、Vite、React Flow、Recharts |
| 端口 | 前端 3200、后端 8000、Airflow 18080(见文档 0.4) |

## 快速启动

### 1. 后端(8000)

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

或:

```bash
./scripts/run_backend.sh
```

### 2. 前端(3200)

```bash
cd frontend
npm install
npm run dev
```

或:

```bash
./scripts/run_frontend.sh
```

打开 <http://127.0.0.1:3200>;OpenAPI 文档:<http://127.0.0.1:8000/docs>。

### 3. 重置演示数据

```bash
./scripts/reset_demo.sh --yes
```

仅删除 `backend/data/iqe_demo.db*`(Demo 自己生成的数据),不会触碰任何设备配置或密码。

## 测试

```bash
cd backend
.venv/bin/pytest -q          # 40 项测试

cd ../frontend
npm run build                # TypeScript + Vite 构建
```

## 目录结构

```
AI_Agent_Pipeline/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口与 API
│   │   ├── models/event.py         # 文档 3.1 标准事件信封
│   │   ├── plugins/                # 8 类插件 + 6 个 Agent + 默认 Prompt
│   │   ├── services/               # 编排、降级、审批、知识库
│   │   ├── db.py                   # SQLite 持久化
│   │   └── seed.py                 # 文档 4.2 流水线模板
│   └── tests/                      # 40 项自动化测试
├── frontend/src/                   # 8 个演示页面
├── docs/
│   ├── 产品设计说明.md
│   ├── 操作指南.md
│   └── 待确认问题清单.md
└── scripts/                        # 启动 / 重置脚本
```

## 可选运行参数

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `IQE_API_TOKEN` | 空 | 设置后 `/api/*` 需要 `Authorization: Bearer <token>`;前端对应 `VITE_API_TOKEN` |
| `IQE_TIMEZONE` | 服务端本地时区 | “今日”统计时区,例如 `Asia/Shanghai` |
| `IQE_AGENT_TIMEOUT_SECONDS` | 120 | 单个 Agent 执行超时;超时失败 Run 并写死信 |
| `IQE_MAX_CONCURRENT_RUNS` | 8 | 内置编排器最大并发 Run 数;也可在插件配置中修改 |

## 重要说明

1. **确认结果**:文档未定义的 API、Agent payload、Qoder CN/Airflow 细节、知识库算法、指标口径等已按推荐方案确认,结论见 [docs/待确认问题清单.md](docs/待确认问题清单.md) F 节;代码中已确认基线以 `【已确认 Q编号】` 标记,真实外部契约仍保留 `【待确认】`。
2. **模拟指标**:Mock 模式下 `latency_ms` 按文档场景 1/3 做业务耗时模拟,UI 标注“模拟业务耗时”;实验面板的 8/12/45 分钟来自文档基线;Trace、仪表盘、实验面板均标注 TAT 来源。
3. **安全边界**:Demo 面向本机演示,后端绑定 `127.0.0.1`,默认无登录/权限体系;支持可选 Bearer Token(Q13);插件密钥在响应与日志中脱敏,配置严格按 `config_schema` 校验。**不修改任何设备密码。**
4. **Airflow 真实执行**:当前无 DAG 回调契约(Q8),`delegate_execution` 默认关闭,插件完成触发/查询/停止与降级,不伪造“Airflow 实际执行成功”。场景 4 演示的是平台降级能力与插件独立性。
5. **Qoder CN**:按 OpenAI 兼容接口实现(Q9)。未配置凭据时自动使用 Mock LLM,插件页显示红色“不可用”属于预期状态。
6. **知识库**:入库保存日志摘要、Triage 根因与分类;检索使用词频余弦 + 查询覆盖率,阈值 0.35、TopK 3。
7. **Prompt**:6 个 Agent 的默认 Prompt 在 `backend/app/plugins/agents/prompts.py`;插件配置页与画布阶段均可修改,优先级为阶段 > 插件 > 默认;Trace 记录 `prompt_version/prompt_source/prompt_hash`。Mock LLM 不依赖 Prompt 内容。
