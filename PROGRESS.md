# IQE-Agent Platform Demo 进度日志

> **最后更新**: 2026-11-05 15:00  
> **当前会话目标**: 完成场景 3 知识库加速的端到端验证

---

## 当前快照

| 指标 | 状态 |
|---|---|
| **最新 commit** | `66d9088` — feat: 完善生产化输入源、画布与飞书通知 |
| **后端测试** | ✅ 57/57 passed (1.52s) |
| **前端构建** | ✅ tsc + vite build 通过 |
| **服务状态** | 后端 :8000 / 前端 :3200 可启动 |
| **Airflow 集成** | ✅ 真实轮询已验证 (v3.3.1, 端口 18080) |
| **Qoder CN LLM** | ✅ 真实代理已接入 (DeepSeek-Flash via :3000) |
| **飞书通知** | ✅ Webhook + 应用双模式已实现 |

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

---

## 进行中 🔄

### 场景 3 知识库加速验证 (70%)
- [x] 知识库入库接口 — Reviewer 阶段自动保存案例摘要 + Triage 结论
- [x] 知识库检索接口 — 词频余弦相似度，TopK=3，阈值=0.35
- [ ] **卡点**: 场景 3 复现步骤未跑通
  - **现象**: 案例 B 的 Triage 置信度未从 0.75 提升到 0.92
  - **已尝试**: 检查了入库内容，摘要字段完整；怀疑检索时 query 构造不一致
  - **下一步**: 对比案例 A 入库时的原始日志 vs 案例 B 检索时的 query 向量

---

## 已知问题 ⚠️

| 编号 | 问题 | 影响 | 优先级 |
|---|---|---|---|
| I1 | 场景 3 知识库加速未端到端验证 | 无法演示"置信度提升 + 耗时缩短" | P0 |
| I2 | `test_pagination_edge_case` 在空结果集时返回 500 | 不影响 Demo 场景，但测试用例失败 | P2 |
| I3 | 实验面板的 TAT 来源标注不清晰 | 管理层可能混淆"文档基线"与"实测值" | P1 |

---

## 下一步 📋

1. **[P0]** 修复场景 3 知识库检索 query 构造逻辑，确保案例 B 能命中案例 A 的入库知识
2. **[P1]** 在实验面板的对比图表中明确标注"文档基线 / 模拟指标 / 实测值"三种来源
3. **[P2]** 跑通 5 个演示场景的完整验收流程，记录每个场景的 Trace ID 和截图
4. **[P3]** 清理 `backend/app/plugins/` 下的 `__pycache__` 和 `.pyc` 文件

---

## 验证记录 🧪

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

新会话接手时，请按以下顺序读取：

1. **读本文档** — 了解当前进度和卡点
2. **读 `docs/待确认问题清单.md`** — 了解已确认/待确认的决策
3. **读 `IQE-Agent-Platform-Demo开发指导文档_v2.md`** — 了解产品需求和架构设计
4. **跑 `./scripts/verify.sh`** — 验证仓库处于一致状态
5. **从"下一步"第 1 项开始工作** — 修复场景 3 知识库检索逻辑
