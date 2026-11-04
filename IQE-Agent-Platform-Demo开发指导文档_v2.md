# AI Agent 插件化编排平台 Demo 开发指导文档 v2.5

> **文档定位**:面向管理层/决策者的 1-2 周快速 Demo,展示业务价值 + 技术可行性
> **核心原则**:万物插件(所有能力都是插件,平台内核只做编排)
> **集成策略**:真实集成 Airflow(输入源) + Qoder CN(LLM),保留 mock 降级方案
> **版本**:v2.5 | 2026-11-03

---

## 产品定位

**IQE-Agent Platform 是一个独立的 AI Agent 编排平台**,不依赖任何特定的 CI/CD 或调度系统。

- **Airflow、Jenkins、GitLab CI 等都是可选的输入源插件**,不是平台的前提条件
- **平台自带编排引擎**,可以独立运行流水线
- **如果客户已有 Airflow**,可将其配置为输入源插件,实时监控全部或指定 DAG 的失败运行并自动触发 Agent 流水线
- **如果客户没有 Airflow**,平台可以直接运行,无需额外基础设施

**核心价值**: 一个平台,任意集成,不被技术栈锁定。

---

## 0. 文档定位与目标

### 0.1 目标受众
- **主要**:管理层/决策者(关注 ROI、效率提升、风险控制)
- **次要**:技术团队(关注架构、可扩展性、集成成本)

### 0.2 Demo 核心目标
1. **业务价值**:展示端到端自动化带来的 TAT 缩短、人力节省、质量提升
2. **技术可行性**:证明插件化架构可行,真实系统(Airflow/Qoder CN)可集成
3. **战略灵活性**:展示"万物插件"带来的技术栈无关性(可换编排器、可换 LLM)
4. **产品独立性**:展示平台不依赖任何外部系统,Airflow/Jenkins 都是可选插件

### 0.3 开发约束
- **周期**:1-2 周(10 个工作日)
- **团队**:1 全栈 + 1 后端(或 1 人全栈)
- **优先级**:演示场景 > 功能完整 > 代码质量

### 0.4 本机端口约定(2026-11-02 已核验)
| 用途 | 端口 | 说明 |
|---|---|---|
| 前端开发服务器(Vite) | **3200** | 原方案 3000 已被本机 qoder-proxy 占用;Vite 默认 5173/5174 也已占用,启动时需显式指定 `--port 3200` |
| 后端 API | **8000** | 当前空闲 |
| Airflow(可选插件,本机真实集成时) | **18080** | 默认 8080 已被本机 Jetty 服务占用,部署 Airflow 时改为此端口 |

> 以上端口在编写本文档时均通过实际绑定测试确认空闲;若后续被其他服务占用,需同步更新本节及附录 B。

---

## 1. 核心原则:万物插件

### 1.1 定义
**万物插件** = 平台内核只保留"编排引擎 + 插件注册中心",所有业务能力(输入、Agent、知识库、工具、编排、LLM、事件、存储)都是可插拔的插件。

### 1.2 为什么选这个原则

| 传统架构 | 万物插件架构 |
|---|---|
| 硬编码 Airflow 集成 | Airflow 是输入源插件之一,可换成 Jenkins/GitLab/文件 |
| 硬编码 OpenAI API | Qoder CN 是 LLM 插件之一,可换成 GPT/本地模型 |
| 换技术栈 = 重写 | 换技术栈 = 换插件 |
| 单点故障风险 | 插件级降级(mock  fallback) |
| 技术锁定 | 技术栈无关 |

### 1.3 Demo 中的具体体现
- **Airflow** 不是"编排引擎",而是"输入源插件"的一个可选实现:轮询失败 DAG Run 并生成 `monitor_alert`
- **Qoder CN** 不是"外部 API",而是"LLM 提供商插件"的一个实现
- **Jenkins** 不是"唯一的输入源",而是"输入源插件"的一个实现
- **编排引擎固定为内置编排器**(v2.4 起不再把 Airflow 作为编排器插件),演示时通过插件开关展示外部依赖可插拔
- 演示时现场切换输入源与 LLM 插件,展示平台独立性

---

## 2. 插件分类体系(8 类)

> 所有插件遵循统一契约:`plugin_id`、`display_name`、`config_schema`、`health()`、生命周期管理

| 插件类型 | 职责 | Demo 示例 | 生产示例 |
|---|---|---|---|
| **输入源插件** | 接收/拉取外部事件 | Mock Jenkins、**Airflow(真实轮询)**、外部日志文件 | 真实 Jenkins Webhook、GitLab CI |
| **Agent 插件** | 执行业务逻辑 | 6 个 IQE Agent | 自定义 Agent |
| **知识库插件** | 存储/检索知识 | 内存向量库 | Milvus/PGVector |
| **工具插件** | 提供原子能力 | Mock Jira | 真实 Jira API |
| **编排引擎插件** | 调度 Agent 执行 | 内置内存编排器 | Temporal/自研调度 |
| **LLM 提供商插件** | 提供推理能力 | Mock LLM | **Qoder CN**(真实集成) |
| **事件总线插件** | 事件投递/订阅 | 内存队列 | Kafka/RabbitMQ |
| **存储插件** | 持久化数据 | SQLite | PostgreSQL + S3 |

> **v2.4 变更**:Airflow 从「编排引擎插件」调整为「输入源插件」,平台只负责实时监控其全部/指定 DAG,出现失败时自动触发 Agent 流水线;编排器固定为内置 `memory_orchestrator`。详见 3.6。

### 2.1 插件依赖声明
每个插件声明依赖的其他插件类型(示例):

```json
{
  "plugin_id": "triage_agent",
  "dependencies": {
    "llm_provider": ["qoder_cn", "mock_llm"],
    "knowledge_base": ["memory_vector", "milvus"],
    "tool": ["log_distiller"]
  }
}
```

---

## 3. 插件契约与接口

### 3.1 标准事件信封(所有插件必须遵守)

```json
{
  "event_id": "uuid",
  "event_type": "monitor_alert | triage_result | repro_result | ticket_draft | review_result | report_item",
  "source_agent": "string",
  "timestamp": "2026-11-02T10:00:00Z",
  "trace_id": "uuid",
  "confidence": 0.0~1.0,
  "evidence_links": ["string"],
  "status": "pending | passed | rejected | need_more_info | handover_human",
  "model_info": {
    "model_loc": "local_strix_halo | cloud_qoder_cn | mock",
    "model_name": "string",
    "latency_ms": 0,
    "cost_token": 0
  },
  "payload": {}
}
```

### 3.2 编排引擎插件接口

> v2.4 起 Demo 仅保留内置 `memory_orchestrator`;Airflow 不再实现该接口,而是按 3.6 作为输入源插件。接口保留以便后续接入 Temporal 等调度器。

```python
class OrchestratorPlugin:
    plugin_id: str
    display_name: str  # "Memory Orchestrator"
    config_schema: dict  # 并发上限等

    def __init__(self, config: dict):
        ...

    async def start_pipeline(self, pipeline_def: dict) -> str:
        # 启动流水线运行,返回 run_id
        ...

    async def get_pipeline_status(self, run_id: str) -> dict:
        # 查询运行状态
        ...

    async def stop_pipeline(self, run_id: str):
        ...
```

### 3.3 LLM 提供商插件接口(以 Qoder CN 为例)

```python
class LLMProviderPlugin:
    plugin_id: str
    display_name: str  # "Qoder CN Cloud"
    config_schema: dict  # API endpoint、API key、model name

    async def chat_completion(self, messages: list, config: dict) -> dict:
        # 调用 Qoder CN API,返回标准响应
        ...

    async def health(self) -> tuple[bool, str]:
        ...
```

### 3.4 插件生命周期
1. **注册**:插件目录扫描或 API 注册
2. **配置**:前端填写 config_schema 表单
3. **健康检查**:调用 `health()` 验证连通性
4. **加载**:实例化插件,注入依赖
5. **运行**:接收事件,执行逻辑,输出事件
6. **卸载**:清理资源,注销实例

### 3.5 Agent System Prompt 配置与覆盖(v2.3 新增)

6 个 IQE Agent 均增加可配置的 `system_prompt`,支持两级覆盖:

| 配置位置 | 字段 | 存储位置 | 优先级 |
|---|---|---|---|
| **插件级** | `plugin.config.system_prompt` | SQLite `plugin_state.config_json` | 中 |
| **阶段级** | `stage.system_prompt` | SQLite `pipelines.definition_json` | 高 |
| **内置默认** | `default_system_prompt` | `backend/app/plugins/agents/prompts.py` | 低 |

最终生效顺序:**阶段级 > 插件级 > 内置默认**。阶段级留空表示不覆盖,继续使用插件配置;插件级为空会被配置校验拒绝。

**默认 Prompt 结构**:每个 Agent 的默认 Prompt 包含角色、输入字段、输出 JSON Schema、边界规则与一个 few-shot 示例。Prompt 版本为 `v1.0.0`,集中维护在 [`prompts.py`](backend/app/plugins/agents/prompts.py),不散落在 Agent 业务代码中。

**运行时行为**:

1. `IQEAgent.call_llm()` 将最终 `system_prompt` 作为 system message,将任务上下文作为 user message;
2. 阶段级覆盖由 `PipelineService` 通过 `registry.create_agent(..., overrides=...)` 注入;
3. Mock LLM 仍按 `task` 规则分支执行,不依赖 Prompt 内容,保证 Demo 可重复;
4. 每次 Agent 输出会在事件 `payload` 中写入:
   - `prompt_version`:Prompt 模板版本;
   - `prompt_source`:`default` / `plugin` / `stage`;
   - `prompt_hash`:最终 Prompt 的 SHA-256 前 12 位;
   - `prompt_text`:本次运行实际发送给模型的 system prompt 快照(v2.4 增强),用于历史 Run 的精确回看;
5. 上述字段只扩展 `payload`,**不改变文档 3.1 的事件信封字段**。

**约束**:

- `system_prompt` 最长 12000 字符;
- 插件级 Prompt 不允许为空;阶段级允许为空以表示“不覆盖”;
- Prompt 中不得写入 API Key、密码等敏感信息;
- Prompt 修改后下一次 Run 生效,无需重启服务;
- 插件配置页与流水线画布均提供多行编辑框,画布保存后写入流水线定义。

---

## 4. Demo 架构设计

### 4.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│              IQE-Agent Platform (独立平台)                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              插件注册中心 & 依赖注入                    │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 输入源   │ │  Agent   │ │ 知识库   │ │ 工具     │       │
│  │ 插件     │ │  插件    │ │ 插件     │ │ 插件     │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 编排引擎 │ │  LLM     │ │ 事件总线 │ │ 存储     │       │
│  │ 插件     │ │  提供商  │ │ 插件     │ │ 插件     │       │
│  │ (内置     │ │          │ │          │ │          │       │
│  │  Memory)  │ │          │ │          │ │          │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              内置编排引擎(默认,无需外部依赖)            │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
    ┌────┴────┐         ┌────┴────┐         ┌────┴────┐
    │ Airflow │         │ Qoder CN│         │ Jenkins │
    │(输入源) │         │ (LLM)   │         │(输入源) │
    └─────────┘         └─────────┘         └─────────┘
         │                    │                    │
    ┌────┴────┐         ┌────┴────┐         ┌────┴────┐
    │  Mock   │         │  Mock   │         │  Mock   │
    │ 降级/Mock│         │ 降级    │         │ 降级    │
    └─────────┘         └─────────┘         └─────────┘
```

**关键设计**:
- 平台**自带编排引擎**,可以独立运行(默认且唯一)
- Airflow 是**输入源插件**,轮询其失败 Run 并触发 Agent 流水线,不承担编排职责
- Jenkins / 外部日志文件同样是输入源插件,统一转换为文档 3.1 标准信封
- 所有外部系统(Airflow/Jenkins/Qoder CN)都有 Mock 降级方案
- 演示时可以先用内置引擎 + Mock 插件跑通,再切换真实输入源/LLM 插件

### 4.2 插件组合示例(IQE 流水线)

```json
{
  "pipeline_id": "iqe_validation_v1",
  "orchestrator": "memory_orchestrator",
  "sources": [
    {"source_id": "mock_jenkins", "plugin_id": "mock_jenkins", "label": "Jenkins / Mock Jenkins", "enabled": true},
    {"source_id": "airflow_prod", "plugin_id": "airflow_input", "label": "Airflow 生产", "enabled": true}
  ],
  "stages": [
    {
      "agent": "monitor_agent",
      "input_source": "mock_jenkins",
      "llm_provider": "qoder_cn",
      "knowledge_base": null
    },
    {
      "agent": "triage_agent",
      "llm_provider": "qoder_cn",
      "knowledge_base": "memory_vector"
    },
    {
      "agent": "reproduction_agent",
      "tool": "jarvis_mock",
      "llm_provider": "qoder_cn"
    },
    {
      "agent": "ticket_agent",
      "tool": "jira_mock",
      "llm_provider": "qoder_cn"
    },
    {
      "agent": "reviewer_agent",
      "llm_provider": "qoder_cn",
      "knowledge_base": "memory_vector",
      "human_gate": true
    },
    {
      "agent": "reporting_agent",
      "llm_provider": "qoder_cn"
    }
  ]
}
```

### 4.3 Prompt 覆盖示例(v2.3 新增)

4.2 的模板保持不变;需要时可在任意阶段增加可选的 `system_prompt`,优先于 Agent 插件配置:

```json
{
  "agent": "triage_agent",
  "llm_provider": "qoder_cn",
  "knowledge_base": "memory_vector_kb",
  "system_prompt": "你是 IQE 流水线的 Triage Agent。只输出 JSON,字段必须包含 category、root_cause、confidence。"
}
```

前端入口:

1. **插件管理 → Agent 插件 → 配置**:修改该 Agent 所有阶段共享的默认 Prompt;
2. **流水线画布 → 选中阶段 → System Prompt**:只覆盖当前流水线阶段;
3. 画布保存后,阶段级 Prompt 写入 `pipelines.definition_json`,下一次 Run 生效。

### 3.6 输入源插件与 Airflow 实时监控(v2.4 新增)

输入源插件在统一基类上增加可选轮询能力:

```python
class InputSourcePlugin(PluginBase):
    async def collect_alerts(self, limit: int, lookback_minutes: int) -> list[dict]:
        # 返回标准事件信封列表;默认空(仅推送型输入源不实现)
        ...
```

**Airflow 输入源插件(`airflow_input`)**

| 配置项 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `api_url` | string | — | Airflow 根地址,如 `http://airflow.example.com:8080` |
| `username` / `password` | string / secret | — | 登录凭据;响应与日志中密码脱敏为 `***` |
| `dag_ids` | multiline | 空 | **留空 = 监控全部 DAG;非空 = 仅监控列出的 DAG**(逗号/换行分隔) |
| `api_version` | enum | `auto` | `auto` 优先探测 REST v2,失败回退 v1 |
| `poll_interval_seconds` | integer | 60 | 后台轮询间隔,最小 5 秒 |
| `lookback_minutes` | integer | 60 | 首次/手动检查的回看窗口 |
| `max_events_per_poll` | integer | 3 | 单轮最多生成的告警数 |
| `max_tasks_per_run` | integer | 3 | 单个失败 Run 最多采集的失败任务数 |
| `timeout_seconds` | integer | 15 | 单次 HTTP 超时 |

**采集流程**:
1. 鉴权:Airflow 3 先 `POST /auth/token` 换取 JWT,后续请求携带 Bearer;Airflow 2 使用 Basic Auth。
2. 查询:按 `dag_ids` 查询 `failed` 的 DAG Run(`order_by=-logical_date`),再枚举失败 TaskInstance 并读取日志。
3. 幂等:以 `dag_id:dag_run_id` 为 `event_key` 写入 SQLite `source_events`;已处理的事件不再重复触发。
4. 生成:每个失败 Run 构造一条 `monitor_alert` 标准信封,`payload` 包含 `case_id/title/job_name/build_number/log_excerpt/artifact_url` 及 `airflow_*` 扩展字段。
5. 触发:通过 `PipelineService.submit_external_event()` 选择启用了该输入源的流水线,创建 Run 并启动内置编排器。

**安全与边界**:
- 日志按 ANSI 控制符清洗,并对 `password/token/api_key/Bearer` 等模式脱敏后再进入事件与 Trace;
- 单个日志最大 6000 字符,避免超长上下文;
- 外部平台凭据只写入本机 SQLite(已 gitignore),不进入代码仓库、不写入日志;
- Airflow 不可用时仅影响该输入源轮询,流水线可在 Mock 输入源下继续演示(文档 7.4)。

**失败 Run 的处理语义**:Reproduction Agent 可能判定为环境问题并拒绝建单,这是文档 4.2 的正常分支,不代表监控失败;Trace 会记录 `rejected` 及原因。

### 3.7 流水线画布自定义(v2.4 新增)

画布支持在不改代码的前提下调整流水线拓扑:

- **输入源节点**:从已注册输入源插件中添加,可启停;支持同一插件多个实例(以 `source_id` 区分);
- **Agent 节点**:从 Agent 插件中添加,允许重复添加同一 Agent;每个节点可配置阶段序号(决定执行顺序)、LLM、知识库、工具、人工卡点、System Prompt;
- **删除/排序**:删除节点后自动重排;阶段序号重复时按画布顺序稳定执行;
- **保存**:写入 `pipelines.definition_json`,下一次 Run 生效;不影响正在运行的 Run;
- **执行映射**:Trace 通过 `source_agent` 顺序游标映射阶段,支持重复 Agent 而不串行错位。

流水线定义新增 `sources` 数组(兼容旧定义):

```json
{
  "pipeline_id": "iqe_validation_v1",
  "orchestrator": "memory_orchestrator",
  "sources": [
    {"source_id": "mock_jenkins", "plugin_id": "mock_jenkins", "label": "Jenkins / Mock Jenkins", "enabled": true},
    {"source_id": "airflow_prod", "plugin_id": "airflow_input", "label": "Airflow 生产", "enabled": true}
  ],
  "stages": [...]
}
```

旧定义迁移规则:若 `sources` 缺失,由首个阶段的 `input_source` 派生;历史 `airflow_orchestrator` 自动归一为 `memory_orchestrator`,历史 `jenkins_webhook` 归一为 `mock_jenkins`。

### 3.8 LLM 提供商真实接入(v2.4 新增)

- 插件 `qoder_cn` 通过 OpenAI 兼容接口访问代理(默认 `http://127.0.0.1:3000/v1`),配置 `api_url/api_key/model/timeout_seconds`;
- 健康检查:`GET {api_url}/models` + Bearer,返回 `Qoder CN 可访问(HTTP 200)`;
- 响应解析:兼容纯 JSON、` ```json ` 代码围栏、以及前后带说明文字的 JSON;均失败时抛出 Schema 校验错误;
- 失败降级:LLM 不可用或返回不符合 Schema 时,按文档 7.4 降级到 Mock LLM,并在 Trace 标注降级原因;
- 真实调用证据:`model_info.model_loc=cloud_qoder_cn`、`model_name=DeepSeek-Flash`,可在 Trace 事件链查看。

> **凭据说明**:Qoder CN 代理的客户端 Key 是代理自身的 `PROXY_API_KEY`;用户提供的 `pt-...` 为上游个人访问令牌,不能直接作为代理客户端 Key。Demo 运行时不修改代理配置,直接复用代理已配置的客户端 Key。

---

## 5. Demo 实现计划(1-2 周)

### 5.1 时间线

| 阶段 | 时间 | 交付物 | 验收标准 |
|---|---|---|---|
| **Phase 1: 核心骨架** | Day 1-3 | 插件基类、注册中心、事件信封、内存编排器、SQLite 存储 | 能加载插件、能跑通空流水线 |
| **Phase 2: 真实集成** | Day 4-7 | Airflow 输入源插件、Qoder CN LLM 插件、6 个 IQE Agent | 能实时监控真实 DAG 失败、能调用真实 LLM |
| **Phase 3: 演示打磨** | Day 8-10 | 前端画布、Trace 页面、实验面板、演示脚本 | 能完整演示 5 个核心场景 |
| **缓冲** | Day 11-14 | 修复问题、文档、预演 | 演示稳定、无阻塞 bug |

### 5.2 Phase 1 详细任务(Day 1-3)

| 任务 | 负责人 | 产出 |
|---|---|---|
| 插件基类定义(8 类) | 后端 | `plugin_base.py` |
| 插件注册中心(目录扫描 + 内存管理) | 后端 | `plugin_registry.py` |
| 标准事件信封 + Schema 校验 | 后端 | `event_schema.py` |
| 内存编排引擎插件 | 后端 | `memory_orchestrator.py` |
| SQLite 存储插件 | 后端 | `sqlite_storage.py` |
| 内存事件总线插件 | 后端 | `memory_event_bus.py` |
| Mock Jenkins 输入源插件 | 后端 | `mock_jenkins.py` |
| 6 个 IQE Agent 骨架(用 mock LLM) | 后端 | `agents/*.py` |
| 前端项目初始化(React + Vite) | 前端 | 项目骨架 |
| 前端路由 + 布局 | 前端 | 页面框架 |

### 5.3 Phase 2 详细任务(Day 4-7)

| 任务 | 负责人 | 产出 |
|---|---|---|
| Airflow 输入源插件(真实 API 集成) | 后端 | `airflow_input.py` |
| 外部日志文件输入源插件 | 后端 | `file_input.py` |
| 输入源后台轮询与自动触发 | 后端 | `source_monitor.py` |
| Qoder CN LLM 插件(真实 API 集成) | 后端 | `qoder_cn_llm.py` |
| Mock 降级逻辑(Airflow/Qoder CN 不可用时自动降级) | 后端 | `fallback_logic.py` |
| 6 个 IQE Agent 完整实现(调用 Qoder CN) | 后端 | Agent 完整逻辑 |
| 内存向量知识库插件 | 后端 | `memory_vector_kb.py` |
| Mock Jira 工具插件 | 后端 | `mock_jira.py` |
| 前端画布页面(React Flow) | 前端 | 拖拽编排界面 |
| 前端 Trace 详情页 | 前端 | 链路追踪界面 |

### 5.4 Phase 3 详细任务(Day 8-10)

| 任务 | 负责人 | 产出 |
|---|---|---|
| 前端仪表盘 | 前端 | 统计卡片 + 流水线列表 |
| 前端实验面板 | 前端 | 本地 vs 云端对比图表 |
| 演示脚本编写 | 全栈 | 5 个场景的逐步操作指南 |
| 演示数据准备 | 全栈 | 20-30 个预置失败案例 |
| 集成测试 | 全栈 | 端到端测试用例 |
| 演示预演 | 全栈 | 至少 3 次完整预演 |

---

## 6. 核心演示场景(管理层视角)

> 每个场景控制在 3-5 分钟,总演示时长 20-25 分钟

### 场景 1: 端到端自动化(展示效率)
**目标**:展示从 CI 失败到工单创建的全自动流程
**操作**:
1. 打开仪表盘,显示"今日待处理失败:0"
2. 点击"推送模拟 CI 失败事件"
3. 切换到 Trace 页面,展示流水线自动流转(Monitor → Triage → Reproduction → Ticket → Reviewer → Reporting)
4. 高亮显示每个阶段的耗时
5. 最终显示"工单已创建,TAT: 8 分钟(人工平均 45 分钟)"

**关键信息**:TAT 缩短 80%,无需人工介入

### 场景 2: 人工卡点(展示可控性)
**目标**:展示 Reviewer 卡点防止错误工单
**操作**:
1. 推送一个低置信度案例(置信度 0.6)
2. 展示事件在 Reviewer 节点暂停,状态变为"handover_human"
3. 打开 Trace 详情,展示 Agent 的推理过程和证据
4. 点击"驳回",填写原因"证据不足"
5. 展示系统记录驳回原因,事件标记为"rejected"

**关键信息**:Agent 不直接写 Jira,人工有最终决定权

### 场景 3: 知识库加速(展示学习能力)
**目标**:展示系统越用越准
**操作**:
1. 推送第一个"驱动兼容性"失败案例,展示 Triage 耗时 3 分钟,置信度 0.75
2. 在 Reviewer 节点点击"标记入库知识库"
3. 推送第二个相似的"驱动兼容性"失败案例
4. 展示 Triage 耗时降至 30 秒,置信度提升至 0.92
5. 展示知识库检索结果:"命中历史案例 #123"

**关键信息**:知识库命中后,效率提升 6 倍,准确率提升 23%

### 场景 4: 平台独立性(展示不依赖外部系统)
**目标**:展示平台可以独立运行,不依赖 Airflow/Jenkins 等外部系统
**操作**:
1. 打开插件管理页面,显示当前编排引擎是"内置编排引擎"(默认且唯一)
2. 展示流水线正常运行,无需任何外部系统(数据源页 Mock Jenkins 推送)
3. 在插件管理中启用 Airflow 输入源,填写 Airflow URL、凭据与 DAG 列表(DAG 留空 = 全部监控)
4. 在数据源页点击"立即检查",展示真实 Airflow 失败 Run 被转换为 `monitor_alert` 并自动创建 Trace
5. 禁用 Airflow 输入源,流水线仍可由 Mock Jenkins/外部日志文件触发,不影响演示
6. 同样演示 LLM 插件切换(Qoder CN → Mock LLM)

**关键信息**:平台自带核心能力,外部系统是可选增强,不是前提条件

### 场景 5: 成本对比(展示 ROI)
**目标**:展示本地 vs 云端模型的成本效益
**操作**:
1. 打开实验面板,选择"IQE Validation 流水线"
2. 展示两组数据:
   - Qoder CN Cloud: 平均 TAT 8 分钟,单票成本 ¥2.5,置信度 0.88
   - Mock Local(模拟 Strix Halo): 平均 TAT 12 分钟,单票成本 ¥0.3,置信度 0.85
3. 展示折线图:随着知识库积累,本地模型置信度逐渐接近云端
4. 给出建议:"高频场景用本地,复杂场景用云端"

**关键信息**:混合策略可降低成本 70%,质量损失 <5%

---

## 7. 开发约束与最佳实践

### 7.1 插件隔离
- 每个插件运行在独立进程/线程(Phase 1 可放宽,Phase 2 必须实现)
- 插件崩溃不影响其他插件(异常捕获 + 降级)
- 插件配置隔离(每个插件独立 config,不共享全局状态)

### 7.2 错误处理
- 插件输出 Schema 校验失败 → 死信队列,Trace 标记异常
- 置信度低于阈值(默认 0.7) → 自动流转人工节点
- 外部服务不可用(Airflow/Qoder CN) → 自动降级到 mock 插件
- 所有错误记录到 Trace,前端可查看

### 7.3 可观测性
- 每个插件暴露 `health()` 接口,前端显示连接状态
- 每个事件记录 `model_info`(模型、延迟、成本)
- 每个 Agent 事件在 `payload` 中记录 `prompt_version / prompt_source / prompt_hash`,用于 Prompt 审计与回滚定位
- Trace 页面展示完整链路(输入、输出、耗时、置信度、Prompt 来源)
- 实验面板展示本地 vs 云端对比

### 7.4 Mock 降级策略
| 真实服务 | 降级方案 | 触发条件 |
|---|---|---|
| Airflow(输入源) | 跳过本轮轮询 / 使用 Mock Jenkins 或文件输入源 | Airflow API 不可用、鉴权失败或超时 |
| 编排引擎 | 内置 `memory_orchestrator` | 插件缺失或禁用(v2.4 起为唯一编排器) |
| Qoder CN | Mock LLM | Qoder CN API 不可用、超时或返回不符合 Schema |
| 真实 Jenkins | Mock Jenkins | 无真实 Jenkins 环境 |
| 真实 Jira | Mock Jira | 无真实 Jira 环境 |
| Milvus | 内存向量库 | 无真实 Milvus 环境 |

---

## 8. 验收标准

### 8.1 功能验收
- [ ] 能加载 8 类插件,插件列表页面正常显示
- [ ] 能创建 IQE 流水线(6 个 Agent + 内置编排 + Qoder CN LLM)
- [ ] 能推送模拟 CI 事件,流水线自动流转
- [ ] Airflow 作为输入源插件,可配置平台地址/凭据/DAG 列表(DAG 留空 = 全部监控)
- [ ] 能实时检查真实 Airflow 失败 Run,生成 `monitor_alert` 并自动触发流水线
- [ ] 相同 `dag_id:dag_run_id` 不会重复触发(幂等)
- [ ] 画布可新增/删除输入源,可新增/删除/排序 Agent,允许重复 Agent
- [ ] 支持上传外部运行/错误日志文件并触发流水线
- [ ] Trace 页面能查看完整链路(输入、输出、耗时、置信度)
- [ ] 低置信度事件自动流转人工节点
- [ ] Reviewer 能驳回/批准工单
- [ ] 知识库能检索、新增条目
- [ ] 实验面板展示本地 vs 云端对比
- [ ] Agent 插件配置页可修改 `system_prompt` 并持久化
- [ ] 流水线画布可修改阶段级 `system_prompt`,保存后下一次 Run 生效
- [ ] Trace 事件 payload 可查看 `prompt_version / prompt_source / prompt_hash`
- [ ] 仪表盘 Agent 抽屉展示本次运行实际使用的 System Prompt 快照及来源
- [ ] Run 完成/驳回/失败后可向飞书群或个人发送汇总卡片,同一状态只发送一次
- [ ] 飞书通知未配置/发送失败时不影响流水线终态,投递状态可查询
- [ ] 飞书 Webhook URL 与应用密钥在响应/日志中脱敏

### 8.4 真实集成验收证据(v2.4,2026-11-03)

| 项目 | 环境 | 结果 |
|---|---|---|
| Airflow 健康检查 | Airflow 3.3.1 测试环境 | `Airflow 3.3.1 可访问,发现 19 个 DAG` |
| 指定 DAG 监控 | `test_flash_attention_flow` | 失败 Run 被识别,生成 `monitor_alert`,自动创建 Trace |
| Airflow 鉴权 | Airflow 3 REST v2 + JWT | `POST /auth/token` 成功,401 自动刷新 |
| 真实 LLM 健康检查 | `http://127.0.0.1:3000/v1` | `Qoder CN 可访问(HTTP 200)` |
| 真实 LLM 端到端 | `DeepSeek-Flash` | 6 个 Agent 均记录 `cloud_qoder_cn`,工单成功创建 |
| LLM 降级 | 关闭/不可用 | Trace 标注 `fallback_reason`,自动使用 Mock LLM |
| 自动化测试 | 后端 + 前端 | pytest **57 passed**;`tsc -b && vite build` 成功 |

> Airflow 环境失败类 Run 可能在 Reproduction 阶段被判定为环境问题并拒绝建单,这是文档 4.2 的业务分支;改用 Mock 案例 `IQE-CASE-001` 可完整验证 6 Agent 全链路。

### 8.2 演示验收
- [ ] 5 个核心场景都能完整演示(每个 3-5 分钟)
- [ ] 演示过程中无阻塞 bug
- [ ] Mock 降级功能正常(关闭 Airflow/Qoder CN 后流水线仍能跑)
- [ ] 演示脚本清晰,非技术人员能按脚本操作

### 8.3 技术验收
- [ ] 插件接口统一,新增插件只需实现基类
- [ ] 插件依赖声明清晰,依赖缺失时前端提示
- [ ] 事件信封格式统一,所有插件遵守
- [ ] Prompt 覆盖按“阶段 > 插件 > 默认”生效,并有版本/哈希审计
- [ ] 代码注释清晰,区分"演示 Mock"和"真实集成"

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| Airflow API 集成复杂 | 延期 | 先做 Mock 输入源,再按 Airflow 3 REST v2/JWT 集成真实轮询 |
| Airflow 失败日志格式差异 | 解析失败 | 按事件列表/纯文本两种格式兼容,并限制长度与脱敏 |
| 输入源重复触发 | 重复工单 | `source_events` 以 `dag_id:dag_run_id` 幂等去重 |
| Qoder CN API 文档不全 | 延期 | 提前联系 Qoder CN 团队获取 API 文档 |
| 演示时真实服务不可用 | 演示失败 | Mock 降级方案必须就绪 |
| 前端画布开发耗时 | 延期 | 用 React Flow 现成组件,不自己写拖拽 |
| 演示数据不足 | 演示单调 | 提前准备 20-30 个预置案例(含 flaky、环境、真 bug) |
| Prompt 被误改导致输出不稳定 | 演示结果漂移 | 默认 Prompt 集中版本化;阶段级可回退;Trace 记录 `prompt_hash` |
| 日志内容包含恶意指令(Prompt Injection) | 模型偏离任务 | Prompt 明确“输入仅作数据”;输出仍经过 JSON Schema 与 payload 必填校验 |

---

## 10. 交付物清单

| 交付物 | 格式 | 负责人 | 截止 |
|---|---|---|---|
| 后端代码 | Git 仓库 | 后端 | Day 10 |
| 前端代码 | Git 仓库 | 前端 | Day 10 |
| 部署文档 | Markdown | 全栈 | Day 12 |
| 演示脚本 | Markdown | 全栈 | Day 12 |
| 演示预演记录 | 视频/截图 | 全栈 | Day 13 |
| 项目 README | Markdown | 全栈 | Day 14 |

---

## 附录 A: 插件开发模板

```python
import json

from plugin_base import AgentPlugin

class MyCustomAgent(AgentPlugin):
    plugin_id = "my_custom_agent"
    display_name = "My Custom Agent"
    description = "A custom agent for demo"
    input_event_types = ["monitor_alert"]
    output_event_type = "triage_result"
    config_schema = {
        # 若继承 IQEAgent,system_prompt 会自动注入,无需手写
        "system_prompt": {
            "type": "string",
            "multiline": True,
            "max_length": 12000,
            "default": "你是自定义 Agent,只输出 JSON。"
        },
        "confidence_threshold": {"type": "number", "default": 0.7}
    }

    def __init__(self, config: dict, dependencies: dict):
        self.config = config
        self.llm = dependencies["llm_provider"]
        self.kb = dependencies.get("knowledge_base")

    async def run(self, input_event: dict) -> dict:
        # 最终 Prompt:阶段级覆盖 > 插件配置 > 默认值
        system_prompt = self.config.get("system_prompt") or "你是自定义 Agent,只输出 JSON。"
        # 调用 LLM
        response = await self.llm.chat_completion(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": json.dumps(input_event)}],
            {},
        )
        # 检索知识库
        if self.kb:
            context = await self.kb.search(...)
        # 返回标准事件信封
        return {
            "event_type": self.output_event_type,
            "confidence": 0.85,
            "payload": {...}
        }
```

---

## 附录 B: 演示脚本模板

```
# 场景 1: 端到端自动化
1. 打开浏览器,访问 http://localhost:3200
2. 点击"仪表盘",显示"今日待处理失败:0"
3. 点击"数据源管理" → "Mock Jenkins" → "推送模拟事件"
4. 点击"Trace 列表",刷新,显示新 trace
5. 点击 trace_id,进入详情页
6. 展示流水线流转动画(Monitor → Triage → Reproduction → Ticket → Reviewer → Reporting)
7. 高亮显示每个阶段耗时
8. 最终显示"工单已创建,TAT: 8 分钟"
9. 说:"这就是端到端自动化的效果,从失败到工单只需 8 分钟,人工平均需要 45 分钟"
```

---

**文档版本历史**:
- v1.0 (2026-10-30): 初始版本,4 类插件,面向技术团队
- v2.0 (2026-11-02): 万物插件原则,8 类插件,面向管理层,1-2 周快速 Demo
- v2.1 (2026-11-02): 强调产品独立性,平台自带编排引擎,Airflow/Jenkins 为可选插件
- v2.2 (2026-11-02): 按本机端口占用情况调整——前端端口 3000 → 3200,新增端口约定(后端 8000、Airflow 18080)
- v2.3 (2026-11-02): 新增 Agent System Prompt 配置与两级覆盖(插件级 / 阶段级)、默认模板、Prompt 版本与哈希审计;补充画布与插件配置入口、验收项与风险
- v2.4 (2026-11-03): Airflow 从编排引擎插件改为输入源插件(支持全部/指定 DAG、Airflow 3 REST v2 + JWT、失败 Run 自动触发与幂等去重);新增外部日志文件输入源;流水线画布支持新增输入源与 Agent(含重复 Agent);补充 Qoder CN 真实接入(DeepSeek-Flash、JSON 围栏解析、Schema 失败降级);新增真实集成验收证据,测试增至 47 项
- v2.5 (2026-11-03): 新增 `feishu_notifier` 工具插件(Webhook / 自建应用双模式)、`NotificationService` 终态异步通知、`run_notifications` 按状态幂等与失败隔离;Webhook URL/应用密钥脱敏;测试增至 57 项
