import { useEffect } from "react";
import { Icon } from "../Icon";
import { JsonView } from "./JsonView";
import { Badge, ConfidenceMeter, StatusBadge } from "./Ui";
import type { EventEnvelope, PipelineStage, RunInfo, TraceStage } from "../types";
import {
  AGENT_LABELS,
  AGENT_SUBTITLES,
  EVENT_TYPE_LABELS,
  MODEL_LOC_LABELS,
  formatLatency,
  payloadString,
  statusLabel,
} from "../utils";

const ANALYSIS_LABELS: Record<string, string> = {
  monitor_summary: "归一化摘要",
  noise: "是否噪声",
  category: "分类",
  root_cause: "根因",
  confidence_reason: "置信度依据",
  kb_hit: "知识库命中",
  kb_entry_id: "知识条目",
  reproduced: "是否复现",
  attempts: "尝试次数",
  reproduction_summary: "复现摘要",
  ticket_title: "工单标题",
  priority: "优先级",
  draft_id: "草案 ID",
  decision: "决策",
  threshold: "阈值",
  review_summary: "审核摘要",
  review_reason: "人工原因",
  reviewed_by: "审核人",
  ticket_key: "工单号",
  tat_seconds: "TAT",
  tat_source: "TAT 来源",
  summary: "摘要",
  prompt_version: "Prompt 版本",
  prompt_source: "Prompt 来源",
  prompt_hash: "Prompt 哈希",
  llm_fallback_reason: "LLM 降级原因",
};

const SUMMARY_KEYS = [
  "monitor_summary",
  "root_cause",
  "reproduction_summary",
  "review_summary",
  "confidence_reason",
  "summary",
  "ticket_title",
];

const PROMPT_SOURCE_LABELS: Record<string, string> = {
  stage: "阶段级",
  plugin: "插件级",
  default: "内置默认",
};

function summaryOf(event: EventEnvelope | null): string {
  if (!event) return "";
  for (const key of SUMMARY_KEYS) {
    const value = event.payload[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "";
}

function truncate(value: string, length: number): string {
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

function toneFor(status: string | undefined): "success" | "warning" | "danger" | "info" | "neutral" {
  if (status === "passed") return "success";
  if (status === "rejected") return "danger";
  if (status === "handover_human" || status === "waiting_human" || status === "need_more_info") {
    return "warning";
  }
  if (status === "running") return "info";
  return "neutral";
}

export function AgentInsightDrawer({
  open,
  stageIndex,
  stage,
  stageConfig,
  event,
  inputEvent,
  run,
  loading,
  onClose,
  onOpenTrace,
}: {
  open: boolean;
  stageIndex: number | null;
  stage: TraceStage | null;
  stageConfig: PipelineStage | null;
  event: EventEnvelope | null;
  inputEvent: EventEnvelope | null;
  run: RunInfo | null;
  loading: boolean;
  onClose: () => void;
  onOpenTrace: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (keyEvent: KeyboardEvent) => {
      if (keyEvent.key === "Escape") onClose();
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open || stageIndex === null) return null;

  const agent = stage?.agent ?? stageConfig?.agent ?? "";
  const running = stage?.status === "running";
  const pending = stage?.status === "pending";
  const summary = summaryOf(event);
  const inputSummary = summaryOf(inputEvent);
  const inputLog = inputEvent ? payloadString(inputEvent.payload, "log_excerpt") : "";
  const prompt = stage?.prompt?.trim() || stageConfig?.system_prompt?.trim() || "";
  const promptSource =
    stage?.prompt_source ?? (stageConfig?.system_prompt ? "stage" : undefined);
  const statusText = running
    ? "执行中"
    : pending
      ? "尚未执行"
      : statusLabel(stage?.status ?? "—");
  const confidence = stage?.confidence;
  const payloadEntries = event
    ? Object.entries(ANALYSIS_LABELS).filter(([key]) => {
        const value = event.payload[key];
        return value !== undefined && value !== null && value !== "" && typeof value !== "object";
      })
    : [];

  return (
    <div className="drawer-backdrop" onMouseDown={onClose}>
      <aside
        className="agent-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`${AGENT_LABELS[agent] ?? agent} 分析过程`}
        onMouseDown={(mouseEvent) => mouseEvent.stopPropagation()}
      >
        <header className="drawer-head">
          <div>
            <span className="eyebrow">AGENT INSIGHT</span>
            <h2>
              {AGENT_LABELS[agent] ?? agent}
              <span className="drawer-stage-index">阶段 {stageIndex + 1}</span>
            </h2>
            <p>{AGENT_SUBTITLES[agent] ?? agent}</p>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="关闭分析面板">
            <Icon name="close" size={16} />
          </button>
        </header>

        <div className="drawer-body">
          <div className="drawer-status-row">
            <Badge tone={toneFor(stage?.status)}>{statusText}</Badge>
            {event ? (
              <Badge tone="neutral">
                {EVENT_TYPE_LABELS[event.event_type] ?? event.event_type}
              </Badge>
            ) : null}
            {typeof confidence === "number" ? (
              <ConfidenceMeter value={confidence} />
            ) : null}
          </div>

          {loading ? <p className="muted">加载运行详情…</p> : null}

          <div className="drawer-chain">
            <section className="drawer-chain-step">
              <span className="drawer-step-label">1 输入</span>
              {inputEvent ? (
                <>
                  <strong>
                    {EVENT_TYPE_LABELS[inputEvent.event_type] ?? inputEvent.event_type} ·{" "}
                    {AGENT_LABELS[inputEvent.source_agent] ?? inputEvent.source_agent}
                  </strong>
                  <p>
                    {inputSummary ||
                      payloadString(inputEvent.payload, "title") ||
                      payloadString(inputEvent.payload, "case_id") ||
                      "已接收上游事件"}
                  </p>
                  {inputLog ? <p className="drawer-log">{truncate(inputLog, 260)}</p> : null}
                </>
              ) : (
                <p>等待上游阶段输出。</p>
              )}
            </section>

            <section className="drawer-chain-step">
              <span className="drawer-step-label">2 处理</span>
              <div className="drawer-meta-grid">
                <span>模型</span>
                <strong>
                  {event
                    ? `${MODEL_LOC_LABELS[event.model_info.model_loc] ?? event.model_info.model_loc} · ${
                        event.model_info.model_name
                      }`
                    : stageConfig?.llm_provider ?? "按阶段配置"}
                </strong>
                <span>耗时</span>
                <strong>
                  {event
                    ? formatLatency(event.model_info.latency_ms)
                    : running
                      ? "执行中"
                      : "—"}
                </strong>
                <span>工具</span>
                <strong>{stageConfig?.tool ?? "—"}</strong>
                <span>知识库</span>
                <strong>{stageConfig?.knowledge_base ?? "—"}</strong>
                <span>人工卡点</span>
                <strong>{stage?.human_gate ? "是" : "否"}</strong>
              </div>
              {prompt ? (
                <>
                  <div className="drawer-prompt-head">
                    <span>生效 Prompt</span>
                    <Badge tone="neutral">
                      {PROMPT_SOURCE_LABELS[promptSource ?? ""] ?? promptSource ?? "未知来源"}
                    </Badge>
                    <span className="drawer-prompt-count">{prompt.length} 字符</span>
                  </div>
                  <pre className="drawer-prompt">{prompt}</pre>
                </>
              ) : (
                <p className="drawer-note">未获取到该阶段的 Prompt 快照。</p>
              )}
            </section>

            <section className="drawer-chain-step">
              <span className="drawer-step-label">3 输出</span>
              {event ? (
                <>
                  <div className="drawer-output-head">
                    <StatusBadge status={event.status} />
                    <strong>{EVENT_TYPE_LABELS[event.event_type] ?? event.event_type}</strong>
                  </div>
                  {summary ? <p>{summary}</p> : null}
                  {payloadEntries.length ? (
                    <div className="payload-grid">
                      {payloadEntries.map(([key, label]) => (
                        <div className="payload-item" key={key}>
                          <span>{label}</span>
                          <strong>
                            {typeof event.payload[key] === "boolean"
                              ? event.payload[key]
                                ? "是"
                                : "否"
                              : String(event.payload[key])}
                          </strong>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {event.evidence_links.length ? (
                    <div className="evidence-links">
                      <span>证据:</span>
                      {event.evidence_links.map((link) => (
                        <code key={link}>{link}</code>
                      ))}
                    </div>
                  ) : null}
                  <JsonView data={event.payload} label="查看完整 payload" />
                </>
              ) : (
                <p>
                  {running
                    ? "Agent 正在执行，结构化输出尚未落库；完成后自动刷新。"
                    : "尚未执行，暂无分析结果。"}
                </p>
              )}
            </section>
          </div>

          {run ? (
            <button className="button button-ghost drawer-trace-link" onClick={onOpenTrace}>
              查看完整 Trace
              <Icon name="arrow" size={14} />
            </button>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
