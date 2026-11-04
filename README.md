# IQE-Agent Platform Demo

面向管理层演示的插件化 AI Agent 编排平台,严格按 `IQE-Agent-Platform-Demo开发指导文档_v2.md`(v2.5)实现。

- **万物插件**:平台内核只做编排,输入源 / Agent / 知识库 / 工具 / 编排引擎 / LLM / 事件总线 / 存储全部可插拔。
- **端到端链路**:Monitor → Triage → Reproduction → Ticket → Reviewer → Reporting。
- **真实集成 + Mock 降级**:Airflow 作为输入源插件实时监控失败 DAG,Qoder CN 作为 LLM 插件真实调用;不可用时自动降级到 Mock。
- **画布自定义**:可新增/删除输入源(Airflow / Mock Jenkins / 外部日志文件),可新增/删除/排序 Agent,允许重复 Agent。
- **实时流水线视图**:仪表盘跟随运行实例动态高亮当前 Agent,点击节点在右侧抽屉查看输入/处理/输出结构化分析。
- **结束通知**:可选飞书工具插件,Run 完成/驳回/失败后向指定群或个人发送汇总卡片,按状态幂等、失败隔离。
- **Prompt 可配置**:6 个 Agent 均有默认 System Prompt,支持插件级与流水线阶段级覆盖,并在 Trace 中记录版本/来源/哈希。
- **完整可观测**:每个事件符合文档 3.1 标准信封,Trace 页面可查看输入、输出、耗时、置信度、模型、输入源与降级原因。

## 5 个演示场景

| 场景 | 入口 | 预期结果 |
|---|---|---|
| 1 端到端自动化 | 数据源 → 场景 1 | 6 个 Agent 自动流转,创建 Mock Jira 工单,TAT 约 8 分钟(模拟) |
| 2 人工卡点 | 数据源 → 场景 2 | 置信度 0.6 < 0.7,Reviewer 暂停;可驳回或批准 |
| 3 知识库加速 | 数据源 → 案例 A → Trace 标记入库 → 案例 B | Triage 置信度 0.75 → 0.92,耗时 3 min → 30 s |
| 4 平台独立性 | 插件管理 / 数据源 / 画布 | Airflow / Qoder CN 不可用时自动降级,流水线照常运行 |
| 5 成本对比 | 实验面板 | 云端 / 本地 / 人工的 TAT、成本、置信度对比 |

详细步骤见 [docs/操作指南.md](docs/操作指南.md)。

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.12、FastAPI、Pydantic v2、asyncio、httpx、SQLite |
| 前端 | React 18、TypeScript、Vite、React Flow、Recharts |
| 端口 | 前端 3200、后端 8000、Airflow 18080(本机;真实测试实例见操作指南) |

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

仅删除 `backend/data/iqe_demo.db*`(Demo 自己生成的数据),不会触碰任何设备配置或密码。注意:重置会清除已保存的 Airflow / Qoder CN / 飞书通知插件配置。

## 飞书通知(可选)

插件管理 → **飞书通知**(默认禁用)→ 配置并启用后,Run 完成/驳回/失败时自动向指定群或个人发送汇总卡片。

| 模式 | 适用 | 必填配置 |
|---|---|---|
| Webhook | 群自定义机器人 | `webhook_url`(群设置 → 群机器人 → 自定义机器人) |
| 应用 | 群或个人 | `app_id`、`app_secret`、`receive_id_type`、`receive_id`;应用需开通 `im:message:send_as_bot` |

- 卡片含状态、案例、分类、置信度、工单号、TAT 来源、失败/驳回原因、Agent 链路和 Trace 按钮;
- `waiting_human` / `stopped` 默认不通知,可在配置中开启;
- 同一 Run 的同一状态只发送一次,失败会重试并记录在 `run_notifications`;
- Webhook URL 与 `app_secret` 在响应和日志中脱敏;插件健康检查只校验配置,不发送测试消息;
- 投递状态查询:`GET /api/runs/{run_id}/notifications`。

## 测试

```bash
cd backend
.venv/bin/pytest -q          # 57 项测试

cd ../frontend
npm run build                # TypeScript + Vite 构建
```

或一键验收:

```bash
./scripts/verify.sh          # 57 passed + tsc/vite build
```

## 目录结构

```
AI_Agent_Pipeline/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口与 API
│   │   ├── models/event.py         # 文档 3.1 标准事件信封
│   │   ├── plugins/                # 8 类插件 + 6 个 Agent + 默认 Prompt
│   │   │   ├── airflow_input.py    # Airflow 输入源(轮询失败 Run)
│   │   │   └── file_input.py       # 外部日志文件输入源
│   │   ├── services/               # 编排、输入源轮询、通知、降级、审批、知识库
│   │   ├── db.py                   # SQLite 持久化
│   │   └── seed.py                 # 文档 4.2 流水线模板
│   └── tests/                      # 57 项自动化测试
├── frontend/src/                   # 8 个演示页面
├── docs/
│   ├── 产品设计说明.md
│   ├── 操作指南.md
│   └── 待确认问题清单.md
└── scripts/                        # 启动 / 重置 / 验收脚本
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
3. **安全边界**:Demo 面向本机演示,后端绑定 `127.0.0.1`,默认无登录/权限体系;支持可选 Bearer Token(Q13);插件密钥在响应与日志中脱敏,配置严格按 `config_schema` 校验。**不修改任何设备密码或外部平台配置。**
4. **Airflow(v2.4)**:作为输入源插件,支持 Airflow 3 REST v2 + JWT(Airflow 2 v1 + Basic Auth 自动回退);`dag_ids` 留空监控全部 DAG,非空仅监控指定 DAG;以 `dag_id:dag_run_id` 幂等去重;失败 Run 自动转换为 `monitor_alert` 并触发流水线。Airflow 不再承担编排职责,编排器固定为内置 `memory_orchestrator`。
5. **Qoder CN**:按 OpenAI 兼容接口实现(Q9),支持 ` ```json ` 代码围栏与说明文字包裹的 JSON 提取;未配置凭据/不可用时自动使用 Mock LLM 并在 Trace 标注降级原因。代理客户端 Key 使用 `PROXY_API_KEY`,用户提供的 `pt-...` 是上游个人访问令牌,不能直接作为代理 Key。
6. **知识库**:入库保存日志摘要、Triage 根因与分类;检索使用词频余弦 + 查询覆盖率,阈值 0.35、TopK 3。
7. **Prompt**:6 个 Agent 的默认 Prompt 在 `backend/app/plugins/agents/prompts.py`;插件配置页与画布阶段均可修改,优先级为阶段 > 插件 > 默认;Trace 记录 `prompt_version/prompt_source/prompt_hash`。Mock LLM 不依赖 Prompt 内容。
8. **画布自定义**:输入源与 Agent 节点均可增删,Agent 允许重复;阶段序号决定执行顺序,保存后下一次 Run 生效;旧流水线定义会在读取时自动迁移。
9. **飞书通知**:`feishu_notifier` 默认禁用,不修改飞书后台配置;真实 Webhook / 应用凭据只保存在本机 SQLite,响应、日志与公共仓库均不包含。实现基线见 [docs/待确认问题清单.md](docs/待确认问题清单.md) H 节。
