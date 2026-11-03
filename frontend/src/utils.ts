const STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  passed: "已通过",
  rejected: "已驳回",
  need_more_info: "需补充信息",
  handover_human: "等待人工",
  running: "运行中",
  waiting_human: "等待人工",
  completed: "已完成",
  failed: "失败",
  stopped: "已停止",
  airflow_triggered: "Airflow 已触发",
};

export type Tone = "success" | "warning" | "danger" | "info" | "neutral";

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function statusTone(status: string): Tone {
  if (["completed", "passed"].includes(status)) return "success";
  if (["waiting_human", "handover_human", "running", "need_more_info"].includes(status)) {
    return "warning";
  }
  if (["rejected", "failed"].includes(status)) return "danger";
  if (["stopped"].includes(status)) return "neutral";
  return "info";
}

export const EVENT_TYPE_LABELS: Record<string, string> = {
  monitor_alert: "监控告警",
  triage_result: "分诊结果",
  repro_result: "复现结果",
  ticket_draft: "工单草案",
  review_result: "审核结果",
  report_item: "指标报告",
};

export const AGENT_LABELS: Record<string, string> = {
  monitor_agent: "Monitor",
  triage_agent: "Triage",
  reproduction_agent: "Reproduction",
  ticket_agent: "Ticket",
  reviewer_agent: "Reviewer",
  reporting_agent: "Reporting",
};

export const AGENT_SUBTITLES: Record<string, string> = {
  monitor_agent: "事件归一化",
  triage_agent: "根因分诊",
  reproduction_agent: "隔离复现",
  ticket_agent: "工单草案",
  reviewer_agent: "质量卡点",
  reporting_agent: "指标输出",
};

export const GROUP_LABELS: Record<string, string> = {
  product_bug: "真 Bug",
  flaky: "Flaky",
  environment: "环境问题",
  driver_compatibility: "驱动兼容",
  low_confidence: "低置信度",
};

export const CATEGORY_LABELS: Record<string, string> = {
  product_bug: "真 Bug",
  flaky: "Flaky",
  environment: "环境问题",
  driver_compatibility: "驱动兼容",
  unknown: "根因未知",
};

export const MODEL_LOC_LABELS: Record<string, string> = {
  mock: "Mock",
  cloud_qoder_cn: "Qoder CN",
  local_strix_halo: "Strix Halo",
};

export const PLUGIN_STATE_LABELS: Record<string, string> = {
  registered: "已注册",
  loaded: "已加载",
  unloaded: "已卸载",
};

export function orchestratorLabel(pluginId: string): string {
  if (pluginId === "memory_orchestrator") return "内置编排引擎";
  if (pluginId === "airflow_orchestrator") return "Airflow";
  return pluginId;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
}

export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms === 0) return "0 ms";
  if (ms >= 60_000) return `${(ms / 60_000).toFixed(1)} min`;
  if (ms >= 1_000) return `${(ms / 1_000).toFixed(1)} s`;
  return `${ms} ms`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function shortId(value: string | null | undefined, length = 8): string {
  if (!value) return "—";
  return value.slice(0, length);
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(0)}%`;
}

export function tatSourceLabel(source: string | null | undefined): string {
  if (source === "simulated_mock") return "模拟业务耗时";
  if (source === "measured") return "实测耗时";
  if (source === "mixed") return "实测/模拟混合";
  return "暂无数据";
}

export function isActiveRun(status: string): boolean {
  return status === "running" || status === "waiting_human";
}

export function payloadString(
  payload: Record<string, unknown> | undefined,
  key: string,
): string {
  const value = payload?.[key];
  return typeof value === "string" ? value : value === undefined || value === null ? "" : String(value);
}

export function payloadNumber(
  payload: Record<string, unknown> | undefined,
  key: string,
): number | null {
  const value = payload?.[key];
  return typeof value === "number" ? value : null;
}
