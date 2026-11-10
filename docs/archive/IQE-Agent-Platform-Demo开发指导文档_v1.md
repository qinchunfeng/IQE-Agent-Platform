# AI Agent CI验证编排平台（IQE-Agent Platform）Demo开发指导文档

> **文档用途**：交付给AI开发助手 / 前端后端开发，用于快速搭建**可演示初始Demo**，用于方案展示
> **目标**：插件化Web平台，支持自定义输入源、自定义Agent、自定义知识库适配器，预置AMD IQE验证流水线模板
> **Demo定位**：最小可用演示版，不追求高并发生产级能力，优先保证流程可跑、页面可交互、链路可观测
> **版本**：v1.0 | 演示Demo版

---

## 1 项目概述

### 1.1 背景与目标

基于AMD IQE Validation AI Agent流水线，封装为通用插件化Web低代码编排平台。

原始流水线链路：`Monitor → Triage → Reproduction → Ticket → Reviewer → Reporting`，在Demo中作为**预置模板**，支持一键导入画布。

**Demo核心演示能力：**

1. 输入源插件化：支持Jenkins、自定义Webhook输入源，可在Web页面新增、配置、连通性测试
2. Agent插件化：内置6个IQE Agent，支持在线编辑Prompt、配置置信阈值、选择模型路由（本地Strix Halo / 云端LLM）；支持新增简易低代码Agent
3. 知识库适配器插件化：内置向量库（Milvus/内存模拟向量库）、结构化库适配器，支持绑定到Agent
4. 可视化拖拽编排画布：串联节点、配置分支、保存流水线版本
5. 事件追踪链路：Trace全链路查看、事件JSON预览、人工干预入口
6. 模型对照实验面板：本地模型vs云端模型指标对比（Demo支持模拟指标）

> **Demo简化约定：**
> - 为降低开发成本，**默认提供内存模拟插件实现**（模拟Jenkins、模拟Jarvis、模拟LLM、模拟向量库），真实后端对接为可选扩展
> - 事件总线Demo阶段优先使用内置内存队列，不强制部署Kafka
> - 权限系统简化：仅区分管理员，不做多租户细粒度RBAC
> - 持久化：使用SQLite存储配置、流水线定义、Trace记录；对象存储用本地文件模拟

### 1.2 Demo 非目标（不做）

- 高并发、集群扩容、生产级死信队列、大规模日志归档
- 完整企业级S3/MinIO、独立Jarvis集群、真实Jira打通（仅模拟回调）
- 复杂SFT微调、大规模知识库离线训练
- 复杂告警通知、邮件日报推送

---

## 2 整体架构（Demo版）

```mermaid
flowchart TB
    Web[Web前端 React+React-Flow] <--> API[FastAPI 后端服务]
    API --> Core[平台核心内核]
    Core --> PluginMgr[插件管理器]
    Core --> EventBus[内存事件总线（Demo）]
    Core --> TraceSvc[Trace&指标服务]
    Core --> DB[(SQLite 数据库)]

    subgraph 插件层【全部可插拔】
        InputPlugin[输入源插件<br/>Jenkins模拟插件 / 自定义Webhook插件]
        AgentPlugin[Agent插件<br/>内置6个IQE Agent + 低代码自定义Agent]
        KBPlugin[知识库适配器插件<br/>内存向量库适配器 / PG模拟适配器]
        ToolPlugin[工具插件<br/>LLM Router模拟插件、Jarvis模拟、Jira模拟]
    end
    PluginMgr <--> 插件层
    EventBus <--> 插件层
```

**核心原则：**
1. 平台内核**无业务硬编码**；IQE流水线只是一份编排模板
2. 所有插件遵循统一抽象接口契约
3. 所有事件统一封装标准信封（即下方的 `event_meta`）

---

## 3 数据契约：全局标准事件信封（强制，所有插件必须遵守）

> 所有输入源输出、Agent输出都必须包裹该外层结构，payload由插件自行定义，用于编排引擎识别流转

```json
{
  "event_id": "uuid",
  "event_type": "monitor_alert | triage_result | repro_result | ticket_draft | review_result | report_item | custom",
  "source_agent": "string",
  "timestamp": "2026-10-30T12:00:00Z",
  "trace_id": "uuid",
  "confidence": 0.0~1.0,
  "evidence_links": ["string"],
  "status": "pending | passed | rejected | need_more_info | handover_human",
  "model_info": {
    "model_loc": "local_strix_halo | cloud_llm | mock",
    "model_name": "string",
    "latency_ms": 0,
    "cost_token": 0
  },
  "payload": {}
}
```

> 各Agent的payload Schema沿用JSON Schema规范，Demo中做校验，输出不符合schema直接标记死信。

---

## 4 插件抽象接口规范（Demo必须实现基类）

> 后端SDK基类，所有插件继承基类，插件管理器动态加载

### 4.1 输入源插件 InputSourcePlugin

```python
class InputSourcePlugin:
    # 插件元信息
    plugin_id: str
    display_name: str
    description: str
    config_schema: dict  # 前端表单JSON Schema，用于用户填写配置

    def __init__(self, config: dict):
        ...

    def health(self) -> tuple[bool, str]:
        # 连通性测试，返回是否正常、提示信息
        ...

    def start(self, event_callback: Callable[[dict], None]):
        # 启动采集，收到事件后调用event_callback输出标准事件信封
        ...

    def stop(self):
        ...
```

**Demo预装输入源：**
1. `mock_jenkins`：模拟Jenkins Webhook，页面可以手动触发推送CI失败事件（用于演示）
2. `custom_webhook`：提供后端HTTP接口，外部系统POST JSON接入

### 4.2 Agent插件 AgentPlugin

```python
class AgentPlugin:
    plugin_id: str
    display_name: str
    description: str
    input_event_types: list[str]  # 可以消费哪些event_type
    output_event_type: str        # 输出event_type
    config_schema: dict

    def __init__(self, config: dict, kb_adapters: list[KBAdapterPlugin]):
        # kb_adapters：绑定的知识库适配器实例
        ...

    async def run(self, input_event: dict) -> dict:
        # 核心执行函数：输入标准事件，输出标准事件信封
        # 内部调用LLM Router、检索知识库、执行工具
        ...

    def validate_output(self, event: dict) -> tuple[bool, str]:
        # 校验输出是否符合schema
        ...
```

**Demo预装6个IQE Agent插件：**
- monitor_agent
- triage_agent
- reproduction_agent
- ticket_agent
- reviewer_agent
- reporting_agent

> **低代码Agent模式**：前端Prompt编辑器，用户填写系统提示词、输入输出类型、置信阈值，后端自动生成Agent实例，无需代码开发。Prompt模板强制输出JSON。

### 4.3 知识库适配器插件 KBAdapterPlugin

```python
class KBAdapterPlugin:
    plugin_id: str
    display_name: str
    config_schema: dict

    def __init__(self, config: dict):
        ...

    def health(self) -> tuple[bool, str]:
        ...

    async def search(self, query: str, top_k: int, filter: dict = None) -> list[dict]:
        # 向量检索，返回匹配条目
        ...

    async def insert(self, metadata: dict, raw_data: str, embedding: list[float] = None):
        # 写入知识库；【重要约束】Agent只读，禁止Agent调用insert；仅Web人工审核页面允许写入
        ...

    async def delete(self, item_id: str):
        ...
```

**Demo预装适配器：**
1. `memory_vector`：内存模拟向量库，重启丢失数据，用于演示检索效果
2. `mock_postgres`：模拟结构化存储，保存历史RCA、工单标签

### 4.4 工具插件 ToolPlugin（LLM Router、Jarvis、Jira）

```python
class ToolPlugin:
    plugin_id: str

    def health(self):
        ...

    async def invoke(self, params: dict) -> dict:
        ...
```

**Demo预装：**
- `llm_router_mock`：模拟本地Strix Halo / 云端模型双路由，可配置返回固定置信度、latency、成本，用于对照实验展示
- `jarvis_mock`：模拟复现任务调度
- `jira_mock`：模拟工单创建、追加评论

---

## 5 后端模块清单（FastAPI）

| 模块 | 功能说明 | Demo简化实现 |
|------|--------|------------|
| 插件管理接口 | 插件列表、加载、卸载、配置保存、连通性测试 | 插件目录扫描 + 内存实例管理 |
| 数据源接口 | 数据源CRUD、绑定流水线、触发模拟事件 | SQLite存配置 |
| 编排接口 | 流水线定义保存、版本管理、模板导入（IQE预置模板） | 编排定义存JSON到数据库 |
| 流水线运行接口 | 启动流水线、事件投递、状态查询 | 内存事件总线异步执行 |
| Trace接口 | 全链路trace查询、单事件详情、人工干预（驳回/补充信息/接管） | SQLite存储trace、event快照 |
| 知识库接口 | 知识库实例CRUD、检索、人工新增条目、条目管理 | 内存向量库+SQLite元数据 |
| 实验指标接口 | 收集每个Agent推理指标、生成对比图表数据 | 模拟指标统计 |
| Webhook接入接口 | 自定义输入源的接收入口 | 简单POST接口 |

> **重要业务约束（代码必须实现）**
> 1. Agent**只读知识库，没有写入权限**；知识库新增条目只能从Web人工审核页面提交
> 2. 置信度低于阈值（默认0.7），事件标记 `handover_human`，流转人工节点，不继续自动流转
> 3. 任何插件输出Schema校验失败，直接进入死信，在Trace页面标记异常

---

## 6 前端Web页面清单（React + React-Flow 拖拽画布）

> 页面风格：技术B端平台，简洁，适合方案演示；优先保证核心页面可用，次要页面轻量化

### 页面1：首页 / 仪表盘
- 流水线列表、运行状态统计、今日Trace数量、人工待处理事件数量
- 快捷入口：新建流水线、导入IQE预置模板、插件市场

### 页面2：插件市场 & 插件管理
- 分组展示：输入源插件 / Agent插件 / 知识库适配器 / 工具插件
- 操作：启用/禁用、配置、测试连通性、查看插件描述
- 低代码Agent创建表单：填写名称、输入输出类型、Prompt、置信阈值、绑定知识库

### 页面3：数据源管理
- 数据源列表：名称、插件类型、连接状态
- 新增数据源表单：选择插件，填写配置，连通性测试，保存
- 【模拟Jenkins数据源】增加按钮：手动推送一条CI失败事件（演示用）

### 页面4：可视化编排画布（核心页面）
- 左侧组件库：已启用的输入源节点、Agent节点、人工审批节点、死信节点
- 画布：拖拽节点、连线；支持分支判断（置信度分支）
- 节点侧边配置面板：
  - Agent节点：在线编辑Prompt、修改置信阈值、选择LLM路由策略、绑定知识库实例
  - 输入源节点：选择已经创建好的数据源
- 顶部操作：保存流水线、另存版本、导入IQE预置模板、启动流水线、停止流水线
- 预置模板一键导入：自动生成 Monitor→Triage→Reproduction→Ticket→Reviewer→Reporting 链路

### 页面5：知识库管理
- 知识库实例列表：适配器类型、连接状态
- 条目列表：检索、查看、新增人工审核条目、标记有效/无效
- 检索测试面板：输入文本，预览向量检索结果

### 页面6：Trace & 链路追踪详情页
- Trace列表：按流水线、时间筛选，展示trace_id、状态、根因、耗时
- Trace详情：时序链路图，每个节点卡片，展示输入事件、输出事件、置信度、模型信息、证据链接
- 人工操作按钮：驳回、补充信息、接管结论、标记入库（知识库）
- 事件JSON查看器，支持复制原始事件

### 页面7：模型实验对比面板（AMD Strix Halo实验演示）
- 选择同一个流水线模板，切换路由策略（local_strix_halo / cloud_llm）
- 展示指标对比卡片：平均TAT、置信度均值、人工介入率、单条推理成本
- 折线图展示指标趋势（Demo为模拟数据）

---

## 7 预置IQE模板（画布导入JSON）

> 后端内置一份编排JSON，用户点击【导入IQE验证模板】自动加载到画布

**节点顺序：**

```
Jenkins模拟输入源 → Monitor Agent → Triage Agent → Reproduction Agent → Ticket Agent → Reviewer Agent → Reporting Agent
```

**分支规则：** 任意节点置信度 < 0.7 → 流转人工节点

---

## 8 Demo 演示流程（给演示人员的标准流程）

1. 打开平台，进入插件市场，确认6个IQE Agent、Jenkins模拟输入源、内存向量库适配器全部启用
2. 数据源管理：新建【Mock Jenkins】数据源，连通测试通过
3. 编排画布：导入【IQE Validation流水线模板】
4. 绑定知识库：选中Triage Agent、Reviewer Agent，绑定内存向量知识库
5. 启动流水线
6. 回到数据源页面，点击【推送模拟CI失败事件】
7. 跳转Trace详情页，查看整条链路自动流转：Monitor告警 → Triage分诊 → 复现 → 草稿工单 → Reviewer审核 → Reporting输出指标
8. 查看每个Agent输出、置信度、模型标记
9. 人工干预：在Review节点，手动驳回或者标记合格，合格后提交入库知识库
10. 实验面板：切换模型路由，对比本地/云端模拟指标

---

## 9 开发优先级 & 迭代顺序

**P0（必须，Demo可跑）**
1. 后端插件基类、插件管理器、内存事件总线
2. 标准事件信封、Schema校验、Trace存储
3. Mock Jenkins输入源、6个IQE Mock Agent（内置Prompt，Mock LLM返回）
4. 内存向量知识库适配器
5. 前端编排画布、导入IQE模板、Trace详情页
6. 数据源管理页面

**P1（演示加分项）**
1. 低代码自定义Agent编辑器
2. 知识库条目管理页面
3. 模型实验对比图表面板

**P2（可选，时间充裕再做）**
1. 真实OpenAI/LLM API对接（替换mock LLM）
2. 真实Milvus向量库对接
3. 真实Webhook外部接入

---

## 10 开发约束 & 风险提示

1. 所有Agent输出必须严格JSON，禁止自由文本，Prompt强制约束
2. 区分【演示Mock实现】和【真实适配器】，代码中做好注释，后续替换真实服务不改动编排内核
3. Demo不做鉴权或者简单单账号密码，不需要复杂RBAC
4. 所有模拟逻辑增加标识，Trace中标记 `mock=true`，避免混淆真实能力
5. 编排引擎只依赖事件信封，不感知Agent内部逻辑，保证插件热插拔

---

## 11 交付物验收标准（Demo做完后验证）

- [x] 可以在Web页面新增数据源、连通测试、推送模拟CI事件
- [x] 一键导入IQE预置6Agent流水线模板，画布链路正常
- [x] 启动流水线，模拟CI事件流入，自动按顺序流转所有Agent
- [x] Trace页面可以查看全链路每一步输入输出、置信度、模型信息
- [x] 支持人工在任意节点接管、驳回、标记入库知识库
- [x] 可以新建低代码Agent，添加到画布，参与编排
- [x] 可以切换知识库适配器绑定到Agent
- [x] 实验面板展示本地/云端模型指标对比
