import type {
  AirflowDag,
  DashboardData,
  DemoCase,
  ExperimentSummary,
  KnowledgeEntry,
  PipelineDefinition,
  PipelineRecord,
  PluginCategory,
  PluginInfo,
  PushEventResult,
  SourcePollItem,
  TraceDetail,
  TraceSummary,
} from "./types";

const BASE = "/api";
// 【已确认 Q13】默认空 Token 表示本机 Demo 无鉴权;与后端 IQE_API_TOKEN 对应。
const API_TOKEN = import.meta.env.VITE_API_TOKEN?.trim() ?? "";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function detailToMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          const loc = "loc" in item && Array.isArray(item.loc) ? item.loc.join(".") : "";
          return `${loc ? `${loc}: ` : ""}${String((item as { msg: unknown }).msg)}`;
        }
        return JSON.stringify(item);
      })
      .join("; ");
  }
  return "请求失败";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      message = detailToMessage(body?.detail ?? body) || message;
    } catch {
      // 保留 HTTP 状态信息
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string; version: string }>("/health"),
  dashboard: () => request<DashboardData>("/dashboard"),
  experiments: () => request<ExperimentSummary>("/experiments/summary"),

  cases: () => request<{ items: DemoCase[] }>("/input-sources/mock_jenkins/cases"),
  pushCase: (caseId: string) =>
    request<PushEventResult>("/input-sources/mock_jenkins/push", {
      method: "POST",
      body: JSON.stringify({ case_id: caseId }),
    }),

  airflowDags: () => request<{ items: AirflowDag[] }>("/input-sources/airflow_input/dags"),
  pollSource: (pluginId: string, limit = 1, lookbackMinutes?: number) =>
    request<{ items: SourcePollItem[]; count: number }>(
      `/input-sources/${pluginId}/poll`,
      {
        method: "POST",
        body: JSON.stringify({
          limit,
          lookback_minutes: lookbackMinutes ?? null,
        }),
      },
    ),
  uploadLog: (filename: string, content: string) =>
    request<{ filename: string; path: string; size: number }>(
      "/input-sources/file_input/upload",
      {
        method: "POST",
        body: JSON.stringify({ filename, content }),
      },
    ),

  plugins: (checkHealth = true) =>
    request<{ categories: PluginCategory[] }>(`/plugins?check_health=${checkHealth}`),
  plugin: (pluginId: string) => request<PluginInfo>(`/plugins/${pluginId}`),
  configurePlugin: (pluginId: string, config: Record<string, unknown>) =>
    request<PluginInfo>(`/plugins/${pluginId}/config`, {
      method: "POST",
      body: JSON.stringify({ config }),
    }),
  enablePlugin: (pluginId: string) =>
    request<PluginInfo>(`/plugins/${pluginId}/enable`, { method: "POST" }),
  disablePlugin: (pluginId: string) =>
    request<PluginInfo>(`/plugins/${pluginId}/disable`, { method: "POST" }),

  traces: (limit = 50, status?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (status) params.set("status", status);
    return request<{ items: TraceSummary[] }>(`/traces?${params.toString()}`);
  },
  trace: (traceId: string) => request<TraceDetail>(`/traces/${traceId}`),
  reviewRun: (runId: string, action: "approve" | "reject", reason: string) =>
    request<TraceDetail>(`/runs/${runId}/review`, {
      method: "POST",
      body: JSON.stringify({ action, reason: reason || null }),
    }),
  markKnowledge: (runId: string) =>
    request<KnowledgeEntry>(`/runs/${runId}/knowledge`, { method: "POST" }),
  stopRun: (runId: string) => request(`/runs/${runId}/stop`, { method: "POST" }),

  knowledge: (query?: string) =>
    request<{ items: KnowledgeEntry[] }>(
      `/knowledge${query ? `?query=${encodeURIComponent(query)}` : ""}`,
    ),

  pipelines: () => request<{ items: PipelineRecord[] }>("/pipelines"),
  pipeline: (pipelineId: string) => request<PipelineRecord>(`/pipelines/${pipelineId}`),
  savePipeline: (definition: PipelineDefinition) =>
    request<PipelineRecord>("/pipelines", {
      method: "POST",
      body: JSON.stringify(definition),
    }),
};
