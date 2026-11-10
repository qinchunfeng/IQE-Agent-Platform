# Git 提交历史设计规范

> **依据文档**: [lecture-06](file:///home/amd/LAI-D/learn-harness-engineering/docs/zh/lectures/lecture-06-why-initialization-needs-its-own-phase/index.md) — "Git 提交作为检查点"  
> **适用项目**: IQE-Agent Platform Demo  
> **最后更新**: 2026-11-05

---

## 一、提交规范 (Commit Convention)

### 格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### 类型定义

| type | 用途 | 示例 |
|---|---|---|
| `feat` | 新功能 / 新插件 | `feat(airflow): add REST v2 + JWT auto-detection` |
| `fix` | bug 修复 | `fix(kb): correct query vector construction in retrieval` |
| `docs` | 文档更新 | `docs(progress): update PROGRESS.md after Task 15` |
| `test` | 测试更新 | `test(agents): add 18 unit tests for 6 agents` |
| `refactor` | 重构 (不改变功能) | `refactor(plugins): extract common health check logic` |
| `chore` | 构建 / 工具 / 配置 | `chore(init): add PROGRESS.md and FEATURES.md as checkpoint` |
| `perf` | 性能优化 | `perf(kb): optimize cosine similarity calculation` |
| `style` | 代码格式 (不影响逻辑) | `style(frontend): format with prettier` |

### Scope 定义

| scope | 对应模块 |
|---|---|
| `airflow` | Airflow 输入源插件 |
| `file` | 文件输入源插件 |
| `feishu` | 飞书通知插件 |
| `qoder` | Qoder CN LLM 插件 |
| `mock` | Mock 系列插件 (Jenkins / Jira / LLM) |
| `agents` | 6 个 Agent 实现 |
| `kb` | 知识库插件 |
| `orchestrator` | 内存编排器 |
| `event` | 事件信封 / 事件总线 |
| `api` | FastAPI 后端接口 |
| `frontend` | React 前端 |
| `canvas` | 画布自定义功能 |
| `trace` | Trace 页面 / 可观测性 |
| `security` | 安全 / 脱敏 / Token |
| `test` | 测试套件 |
| `docs` | 文档 |
| `init` | 初始化阶段产出 |
| `progress` | 进度日志更新 |

---

## 二、提交消息模板

### 模板 A：功能提交

```bash
feat(airflow): add REST v2 + JWT auto-detection for Airflow 3

- Implement `airflow_input.py` with version auto-detection:
  - Airflow 3: REST v2 + JWT authentication
  - Airflow 2: REST v1 + Basic authentication
- Support `dag_ids` config: empty = monitor all, non-empty = filter
- Deduplicate by `dag_id:dag_run_id` to avoid duplicate triggers
- Convert failed DAG runs to `monitor_alert` events automatically

Progress: Task 7 complete (Airflow input source plugin)
Next: verify with real Airflow 3.3.1 instance on port 18080

Ref: FEATURES.md#task-7, docs/待确认问题清单.md#Q24
```

### 模板 B：Bug 修复提交

```bash
fix(kb): correct query vector construction in retrieval

Problem: Case B's Triage confidence remained 0.75 instead of 
increasing to 0.92 when hitting knowledge base.

Root cause: The query vector constructed during retrieval used 
different tokenization than the one used during case ingestion.

Solution:
- Align query construction with ingestion logic in 
  `memory_vector_kb.py`
- Both now use: case_summary + triage_conclusion + category
- Add test case to verify query-ingestion consistency

Tests: 57/57 passed
Verified: Scene 3 knowledge acceleration now works end-to-end

Ref: PROGRESS.md#进行中-场景-3-知识库加速验证-70
```

### 模板 C：文档/进度更新提交

```bash
docs(progress): update PROGRESS.md after Task 15 verification

Current state:
- Task 15 (Scene 3 KB acceleration): 70% complete
- Ingestion/retrieval APIs implemented
- Blocker: query vector mismatch between ingestion and retrieval

Next steps:
1. Fix query construction logic in `triage_agent.py`
2. Re-run Scene 3 end-to-end verification
3. Update FEATURES.md checkbox status

Ref: PROGRESS.md#2026-11-05-1500
```

### 模板 D：初始化检查点提交

```bash
chore(init): add PROGRESS.md and FEATURES.md as init checkpoint

Per lecture-06 "Git commits as checkpoints" principle, this commit
establishes a clean state for subsequent sessions.

Artifacts added:
- PROGRESS.md: Current progress snapshot with verification records
- FEATURES.md: 28 tasks decomposed with acceptance criteria
- GIT_COMMIT_CONVENTION.md: This file, defining commit standards

Verification:
- [x] `./scripts/verify.sh` passes (57 tests + build)
- [x] Backend :8000 starts successfully
- [x] Frontend :3200 starts successfully
- [x] New session can read PROGRESS.md and continue work

Ref: lecture-06 "初始化的正确做法" section 5
```

---

## 三、检查点策略

### 检查点时机

| 时机 | 提交内容 | 目的 |
|---|---|---|
| **Init 阶段完成** | PROGRESS.md + FEATURES.md + 启动契约 + 示例测试 | 第 6 讲："提交一个干净的 checkpoint" |
| **每个 Task 完成** | 功能代码 + 测试 + 更新 PROGRESS.md / FEATURES.md | 原子工作单元，可独立回滚 |
| **会话结束前** | 当前进度快照 (即使功能未完成) | 第 5 讲："每次下班前写清楚做了什么" |
| **关键决策后** | DECISIONS.md 更新 | 记录"为什么"，避免后续会话重做分析 |
| **Bug 修复后** | 修复代码 + 回归测试 + 更新 PROGRESS.md | 确保问题不再出现 |

### 检查点粒度

**原则**: 每个提交都是一个**可独立验证、可独立回滚**的原子状态。

```
✅ 好的粒度:
- feat(airflow): add REST v2 + JWT auto-detection (1 个插件)
- fix(kb): correct query vector construction (1 个 bug)
- docs(progress): update after Task 15 (1 个进度快照)

❌ 坏的粒度:
- feat: add airflow, file input, feishu notifier, qoder cn (4 个插件混在一起)
- fix: fix kb query and also update progress (2 件事混在一起)
```

---

## 四、提交与状态载体的协作

### 工作流

```
1. 开始工作
   └─→ 读 PROGRESS.md 了解当前状态
   └─→ 读 FEATURES.md 选择下一个 Task

2. 完成一个 Task
   └─→ 更新 FEATURES.md 勾选 checkbox
   └─→ 更新 PROGRESS.md "已完成" 部分
   └─→ git add -A
   └─→ git commit -m "feat(<scope>): <subject>\n\n<body>\n\nRef: FEATURES.md#task-<N>"

3. 会话结束前
   └─→ 更新 PROGRESS.md "当前快照" / "进行中" / "下一步"
   └─→ git add PROGRESS.md FEATURES.md
   └─→ git commit -m "docs(progress): update before session end\n\n<body>"

4. 关键决策后
   └─→ 更新 DECISIONS.md 记录决策原因
   └─→ git commit -m "docs(decisions): record why we chose X over Y\n\n<body>"
```

### 双向追溯

```
PROGRESS.md ──→ Git commit hash (每个已完成条目标注关联 commit)
Git commit ──→ FEATURES.md / PROGRESS.md (提交消息中 Ref: 指向)
```

**示例**:

```markdown
<!-- PROGRESS.md -->
- [x] Task 7: Airflow 输入源插件 (commit: `66d9088`)
```

```bash
# Git commit message
feat(airflow): add REST v2 + JWT auto-detection

Ref: FEATURES.md#task-7, PROGRESS.md#已完成-生产化扩展-2026-11-03---2026-11-04
```

---

## 五、当前项目的 Git 历史

### 已有提交

```bash
$ git log --oneline
66d9088 feat: 完善生产化输入源、画布与飞书通知
eedc0d4 feat: 初始化 IQE-Agent Platform 插件化编排 Demo
```

### 待补充的提交

按第 6 讲要求，初始化阶段应产出一个**干净的 checkpoint 提交**：

```bash
git add PROGRESS.md FEATURES.md GIT_COMMIT_CONVENTION.md
git commit -m "chore(init): add PROGRESS.md and FEATURES.md as init checkpoint

Per lecture-06 principle: 'Git commits as checkpoints'.

Artifacts:
- PROGRESS.md: Current progress with verification records
- FEATURES.md: 28 tasks decomposed with acceptance criteria  
- GIT_COMMIT_CONVENTION.md: Commit standards for this project

Verification:
- [x] ./scripts/verify.sh passes (57 tests + build)
- [x] Backend :8000 starts
- [x] Frontend :3200 starts

Ref: lecture-06 section '初始化的正确做法' item 5"
```

---

## 六、提交消息中的元数据

### 必选字段

| 字段 | 位置 | 用途 |
|---|---|---|
| `type` | 首行 | 快速分类 |
| `scope` | 首行括号内 | 定位模块 |
| `subject` | 首行冒号后 | 一句话说明做了什么 |
| `Ref` | 尾部 | 关联 FEATURES.md / PROGRESS.md 章节 |

### 可选字段

| 字段 | 位置 | 用途 |
|---|---|---|
| `Progress` | body | 标注对应 Task 的完成百分比 |
| `Next` | body | 说明下一步计划 |
| `Tests` | body | 标注测试通过情况 |
| `Verified` | body | 标注端到端验证结果 |
| `Blocker` | body | 标注卡点 (如有) |

---

## 七、提交审查清单

每次提交前，新会话应检查：

```markdown
## 提交前审查清单
- [ ] 提交消息符合 `<type>(<scope>): <subject>` 格式
- [ ] body 说明了"做了什么"和"为什么"
- [ ] Ref: 指向 FEATURES.md 或 PROGRESS.md 的具体章节
- [ ] `./scripts/verify.sh` 通过 (57 tests + build)
- [ ] PROGRESS.md 已更新 (如进度有变化)
- [ ] FEATURES.md 已更新 (如 Task 完成)
- [ ] 没有包含敏感信息 (密钥 / 密码 / Token)
- [ ] 提交粒度合理 (一个提交只做一件事)
```

---

## 总结

Git 提交历史是**不可变的状态轨迹**，与可变的 PROGRESS.md / FEATURES.md 形成互补：

| 载体 | 可变性 | 回答的问题 |
|---|---|---|
| **PROGRESS.md** | ✅ 可变 (覆盖更新) | "现在在哪？卡在哪？" |
| **FEATURES.md** | ✅ 可变 (勾选 checkbox) | "要做什么？怎么算完？" |
| **Git history** | ❌ 不可变 (只能 revert) | "之前发生了什么？为什么？" |

三者协作，确保项目在任何时刻都处于"**可以被全新 agent 接手**"的状态 (第 6 讲核心观点)。
