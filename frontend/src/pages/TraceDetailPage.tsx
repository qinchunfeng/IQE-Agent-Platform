import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Icon } from "../Icon";
import { JsonView } from "../components/JsonView";
import { PipelineStrip } from "../components/PipelineStrip";
import {
  Badge,
  ConfidenceMeter,
  EmptyState,
  SectionCard,
  Spinner,
  StatusBadge,
} from "../components/Ui";
import { useToast } from "../Toast";
import type { EventEnvelope, TraceDetail } from "../types";
import {
  AGENT_LABELS,
  CATEGORY_LABELS,
  EVENT_TYPE_LABELS,
  MODEL_LOC_LABELS,
  formatDateTime,
  formatDuration,
  formatLatency,
  isActiveRun,
  orchestratorLabel,
  payloadString,
  shortId,
} from "../utils";

const HIGHLIGHT_LABELS: Record<string, string> = {
  monitor_summary: "归一化摘要",
  noise: "噪声",
  category: "分类",
  root_cause: "根因",
  kb_hit: "知识库命中",
  reproduced: "已复现",
  attempts: "尝试次数",
  ticket_title: "工单标题",
  priority: "优先级",
  decision: "决策",
  threshold: "阈值",
  review_summary: "审核摘要",
  review_reason: "人工原因",
  reviewed_by: "审核人",
  ticket_key: "工单号",
  tat_seconds: "TAT",
  tat_source: "TAT 来源",
  prompt_version: "Prompt 版本",
  prompt_source: "Prompt 来源",
  prompt_hash: "Prompt 哈希",
  summary: "摘要",
  llm_fallback_reason: "LLM 降级原因",
};

function highlightValue(value: unknown): string {
  if (typeof value === "boolean") return value ? "是" : "否";
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return String(value);
  return String(value);
}

function PayloadHighlights({ event }: { event: EventEnvelope }) {
  const entries = Object.entries(HIGHLIGHT_LABELS).filter(([key]) => {
    const value = event.payload[key];
    return value !== undefined && value !== null && value !== "";
  });
  if (!entries.length) return null;
  return (
    <div className="payload-grid">
      {entries.map(([key, label]) => (
        <div className="payload-item" key={key}>
          <span>{label}</span>
          <strong>{highlightValue(event.payload[key])}</strong>
        </div>
      ))}
    </div>
  );
}

export function TraceDetailPage() {
  const { traceId } = useParams<{ traceId: string }>();
  const [trace, setTrace] = useState<TraceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const navigate = useNavigate();
  const { showToast } = useToast();

  const load = useCallback(async () => {
    if (!traceId) return;
    try {
      const result = await api.trace(traceId);
      setTrace(result);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "加载 Trace 失败");
    } finally {
      setLoading(false);
    }
  }, [traceId]);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 2500);
    return () => window.clearInterval(timer);
  }, [load]);

  const caseId = trace ? payloadString(trace.run.input_event.payload, "case_id") : "";
  const title = trace
    ? payloadString(trace.run.input_event.payload, "title") || caseId || "CI failure"
    : "";
  const reviewer = useMemo(
    () => trace?.events.filter((event) => event.event_type === "review_result").at(-1),
    [trace],
  );
  const canReview = Boolean(trace?.available_actions.includes("approve"));
  const canMark = Boolean(trace?.available_actions.includes("mark_knowledge"));
  const canStop = Boolean(trace?.available_actions.includes("stop"));
  const threshold =
    typeof reviewer?.payload.threshold === "number" ? reviewer.payload.threshold : null;

  const contextHint = useMemo(() => {
    if (!trace) return null;
    if (caseId === "IQE-CASE-019" && trace.run.status === "waiting_human") {
      return "场景 2:该案例置信度 0.6,低于 0.7 阈值。填写“证据不足”并驳回,或批准后创建工单。";
    }
    if (caseId === "IQE-CASE-017" && canMark) {
      return "场景 3 A:点击“标记入库知识库”,然后推送相似案例 B,观察知识库命中效果。";
    }
    if (caseId === "IQE-CASE-018" && trace.events.some((event) => event.payload.kb_hit === true)) {
      return "场景 3 B:知识库已命中,Triage 置信度提升到 0.92,Triage 耗时降至 30 秒。";
    }
    return null;
  }, [trace, caseId, canMark]);

  const review = async (action: "approve" | "reject") => {
    if (!trace) return;
    if (action === "reject" && !reason.trim()) {
      showToast("驳回时请填写原因(文档场景 2)", "error");
      return;
    }
    setBusy(action);
    try {
      const result = await api.reviewRun(trace.run.run_id, action, reason.trim());
      setTrace(result);
      setReason("");
      showToast(action === "approve" ? "已批准并创建工单" : "已驳回,原因已记录", "success");
      await load();
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : "操作失败", "error");
    } finally {
      setBusy(null);
    }
  };

  const markKnowledge = async () => {
    if (!trace) return;
    setBusy("knowledge");
    try {
      await api.markKnowledge(trace.run.run_id);
      showToast("已标记入库知识库", "success");
      await load();
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : "入库失败", "error");
    } finally {
      setBusy(null);
    }
  };

  const pushSimilar = async () => {
    setBusy("similar");
    try {
      const result = await api.pushCase("IQE-CASE-018");
      showToast("相似案例 B 已推送", "success");
      navigate(`/traces/${result.trace_id}`);
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : "推送失败", "error");
    } finally {
      setBusy(null);
    }
  };

  const stopRun = async () => {
    if (!trace) return;
    if (!window.confirm("确认停止该流水线?")) return;
    setBusy("stop");
    try {
      await api.stopRun(trace.run.run_id);
      showToast("流水线已停止", "success");
      await load();
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : "停止失败", "error");
    } finally {
      setBusy(null);
    }
  };

  if (loading) return <Spinner label="加载 Trace…" />;
  if (error && !trace) {
    return (
      <EmptyState
        title="Trace 不存在"
        description={error}
        action={
          <Link className="button button-ghost" to="/traces">
            返回 Trace 列表
          </Link>
        }
      />
    );
  }
  if (!trace) return null;

  const { run, events, ticket, dead_letters } = trace;

  return (
    <div className="page-stack">
      <div className="trace-toolbar">
        <Link to="/traces" className="back-link">
          <Icon name="arrow" size={15} />
          返回 Trace 列表
        </Link>
        <div className="toolbar-actions">
          <button className="button button-ghost button-small" onClick={load} disabled={busy !== null}>
            <Icon name="refresh" size={14} />
            刷新
          </button>
          {canMark ? (
            <button
              className="button button-secondary button-small"
              onClick={markKnowledge}
              disabled={busy !== null}
            >
              <Icon name="knowledge" size={14} />
              {busy === "knowledge" ? "入库中…" : "标记入库知识库"}
            </button>
          ) : null}
          {caseId === "IQE-CASE-017" ? (
            <button
              className="button button-primary button-small"
              onClick={pushSimilar}
              disabled={busy !== null}
            >
              <Icon name="play" size={14} />
              {busy === "similar" ? "推送中…" : "推送相似案例 B"}
            </button>
          ) : null}
          {canStop ? (
            <button className="button button-danger button-small" onClick={stopRun} disabled={busy !== null}>
              <Icon name="stop" size={14} />
              停止
            </button>
          ) : null}
        </div>
      </div>

      <section className="trace-header card">
        <div className="trace-header-top">
          <div>
            <span className="eyebrow">TRACE {shortId(run.trace_id, 12)}</span>
            <h2>{title}</h2>
            <p>
              {payloadString(run.input_event.payload, "job_name")} ·{" "}
              {payloadString(run.input_event.payload, "repository")} ·{" "}
              {formatDateTime(run.started_at)}
            </p>
          </div>
          <div className="trace-header-status">
            <StatusBadge status={run.status} />
            {run.finished_at ? (
              <span className="muted">结束于 {formatDateTime(run.finished_at)}</span>
            ) : (
              <span className="muted">处理中</span>
            )}
          </div>
        </div>

        <div className="trace-meta-grid">
          <div>
            <span>trace_id</span>
            <code>{run.trace_id}</code>
          </div>
          <div>
            <span>run_id</span>
            <code>{run.run_id}</code>
          </div>
          <div>
            <span>流水线</span>
            <strong>{run.pipeline_id}</strong>
          </div>
          <div>
            <span>配置编排器</span>
            <strong>{orchestratorLabel(run.orchestrator_configured)}</strong>
          </div>
          <div>
            <span>实际编排器</span>
            <strong>{orchestratorLabel(run.orchestrator_used)}</strong>
          </div>
        </div>

        {run.fallback_reason ? (
          <div className="alert alert-warning inline-alert">
            <Icon name="alert" size={16} />
            <span>Mock 降级:{run.fallback_reason}</span>
          </div>
        ) : null}
        {contextHint ? (
          <div className="alert alert-info inline-alert">
            <Icon name="spark" size={16} />
            <span>{contextHint}</span>
          </div>
        ) : null}
      </section>

      <div className="metric-grid">
        <div className="metric-card">
          <span>链路置信度</span>
          <ConfidenceMeter value={trace.metrics.confidence} />
          {threshold !== null ? <small>人工阈值 {threshold.toFixed(2)}</small> : null}
        </div>
        <div className="metric-card">
          <span>业务 TAT</span>
          <strong>{formatDuration(trace.metrics.tat_seconds)}</strong>
          <small>
            {trace.metrics.tat_source === "simulated_mock"
              ? isActiveRun(run.status)
                ? "模拟业务耗时(进行中)"
                : "模拟业务耗时"
              : "实测耗时"}
          </small>
        </div>
        <div className="metric-card">
          <span>模型调用</span>
          <div className="model-chips">
            {Object.entries(trace.metrics.model_usage).map(([loc, count]) => (
              <Badge key={loc} tone="info">
                {MODEL_LOC_LABELS[loc] ?? loc} × {count}
              </Badge>
            ))}
          </div>
        </div>
        <div className="metric-card">
          <span>工单</span>
          <strong>{ticket?.ticket_key ?? "未创建"}</strong>
          <small>{ticket ? "Mock Jira" : "等待 Reviewer 通过"}</small>
        </div>
      </div>

      {canReview ? (
        <section className="gate-panel">
          <div className="gate-head">
            <div className="gate-icon">
              <Icon name="shield" size={20} />
            </div>
            <div>
              <h3>人工卡点:Reviewer 等待决策</h3>
              <p>
                {run.human_reason ?? "置信度低于阈值,系统已暂停流水线"}
              </p>
            </div>
            <Badge tone="warning">handover_human</Badge>
          </div>
          <div className="gate-facts">
            <span>
              当前置信度 <strong>{trace.metrics.confidence?.toFixed(2) ?? "—"}</strong>
            </span>
            <span>
              阈值 <strong>{threshold?.toFixed(2) ?? "0.70"}</strong>
            </span>
            <span>
              分类 <strong>{CATEGORY_LABELS[payloadString(reviewer?.payload, "category")] ?? "—"}</strong>
            </span>
          </div>
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="填写审批意见;驳回时请填写原因,例如:证据不足"
            rows={3}
          />
          <div className="gate-actions">
            <button
              className="button button-danger"
              onClick={() => review("reject")}
              disabled={busy !== null || !reason.trim()}
            >
              <Icon name="close" size={15} />
              {busy === "reject" ? "驳回中…" : "驳回"}
            </button>
            <button
              className="button button-primary"
              onClick={() => review("approve")}
              disabled={busy !== null}
            >
              <Icon name="check" size={15} />
              {busy === "approve" ? "处理中…" : "批准并创建工单"}
            </button>
          </div>
          <p className="gate-note">文档场景 2:Agent 不直接写 Jira,人工拥有最终决定权。</p>
        </section>
      ) : null}

      <SectionCard title="流水线进度" subtitle="文档 4.2:6 个 Agent 串行执行">
        <PipelineStrip stages={trace.stages} />
      </SectionCard>

      {ticket ? (
        <SectionCard title="工单" subtitle="Reviewer 通过后由平台写入 Mock Jira">
          <div className="ticket-card">
            <div className="ticket-key">
              <Icon name="ticket" size={20} />
              <strong>{ticket.ticket_key}</strong>
              <Badge tone="success">{ticket.status}</Badge>
            </div>
            <div className="ticket-title">{ticket.title}</div>
            <div className="ticket-meta">
              <span>优先级 {payloadString(ticket.payload, "priority") || "—"}</span>
              <span>分类 {CATEGORY_LABELS[payloadString(ticket.payload, "category")] ?? "—"}</span>
              <span>创建于 {formatDateTime(ticket.created_at)}</span>
            </div>
          </div>
        </SectionCard>
      ) : null}

      {trace.knowledge.length ? (
        <SectionCard title="已入库知识" subtitle="Reviewer 阶段标记入库的历史案例">
          <div className="knowledge-inline">
            {trace.knowledge.map((entry) => (
              <div key={entry.entry_id} className="knowledge-inline-item">
                <div>
                  <strong>{entry.title}</strong>
                  {entry.root_cause ? <p>根因:{entry.root_cause}</p> : null}
                  {entry.summary && entry.summary !== entry.content ? (
                    <p>摘要:{entry.summary}</p>
                  ) : null}
                  <p>{entry.content}</p>
                </div>
                <Badge tone="success">{CATEGORY_LABELS[entry.category] ?? entry.category}</Badge>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {dead_letters.length ? (
        <div className="alert alert-danger">
          <Icon name="alert" size={16} />
          <div>
            <strong>死信队列记录</strong>
            {dead_letters.map((item) => (
              <div key={item.id}>{item.reason}</div>
            ))}
          </div>
        </div>
      ) : null}

      <SectionCard
        title="Trace 事件链"
        subtitle={`共 ${events.length} 个事件 · 每个事件均符合文档 3.1 标准信封`}
      >
        <div className="timeline">
          {events.map((event, index) => (
            <div className="timeline-item" key={event.event_id}>
              <div className="timeline-rail">
                <span className={`timeline-dot dot-${event.status}`} />
                {index < events.length - 1 ? <span className="timeline-line" /> : null}
              </div>
              <article className={`event-card event-${event.status}`}>
                <div className="event-head">
                  <div className="event-agent">
                    <strong>{AGENT_LABELS[event.source_agent] ?? event.source_agent}</strong>
                    <span>{EVENT_TYPE_LABELS[event.event_type] ?? event.event_type}</span>
                  </div>
                  <div className="event-badges">
                    <Badge tone="neutral">{MODEL_LOC_LABELS[event.model_info.model_loc] ?? event.model_info.model_loc}</Badge>
                    <StatusBadge status={event.status} />
                  </div>
                </div>
                <div className="event-meta">
                  <span>
                    <Icon name="clock" size={13} />
                    {formatLatency(event.model_info.latency_ms)}
                  </span>
                  <span>
                    <Icon name="cpu" size={13} />
                    {event.model_info.model_name}
                  </span>
                  <span>{event.model_info.cost_token} tokens</span>
                  <span>{formatDateTime(event.timestamp)}</span>
                </div>
                <div className="event-confidence-row">
                  <ConfidenceMeter value={event.confidence} />
                  <span className="muted">event_id {shortId(event.event_id, 10)}</span>
                </div>
                <PayloadHighlights event={event} />
                {event.evidence_links.length ? (
                  <div className="evidence-links">
                    <span>证据:</span>
                    {event.evidence_links.map((link) => (
                      <code key={link}>{link}</code>
                    ))}
                  </div>
                ) : null}
                <JsonView data={event.payload} label="查看完整 payload" />
              </article>
            </div>
          ))}
        </div>
      </SectionCard>

      {!events.length ? <EmptyState title="暂无事件" /> : null}
      <div className="footnote">
        提示:Mock 模式的 latency_ms 为文档场景模拟耗时(【已确认 Q12】),Trace 页同时展示真实链路;
        事件信封字段严格按文档 3.1。
      </div>
    </div>
  );
}
