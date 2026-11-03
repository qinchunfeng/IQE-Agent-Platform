export type EventType =
  | "monitor_alert"
  | "triage_result"
  | "repro_result"
  | "ticket_draft"
  | "review_result"
  | "report_item";

export type EventStatus =
  | "pending"
  | "passed"
  | "rejected"
  | "need_more_info"
  | "handover_human";

export type ModelLoc = "local_strix_halo" | "cloud_qoder_cn" | "mock";

export interface ModelInfo {
  model_loc: ModelLoc;
  model_name: string;
  latency_ms: number;
  cost_token: number;
}

export interface EventEnvelope {
  event_id: string;
  event_type: EventType;
  source_agent: string;
  timestamp: string;
  trace_id: string;
  confidence: number;
  evidence_links: string[];
  status: EventStatus;
  model_info: ModelInfo;
  payload: Record<string, unknown>;
}

export interface PipelineStage {
  agent: string;
  input_source?: string | null;
  llm_provider?: string | null;
  knowledge_base?: string | null;
  tool?: string | null;
  human_gate?: boolean | null;
  system_prompt?: string | null;
}

export interface PipelineDefinition {
  pipeline_id: string;
  orchestrator: string;
  stages: PipelineStage[];
}

export interface PipelineRecord {
  pipeline_id: string;
  definition: PipelineDefinition;
  created_at: string;
  updated_at: string;
}

export interface PluginSchemaField {
  type: "string" | "number" | "integer" | "boolean";
  label?: string;
  description?: string;
  default?: unknown;
  required?: boolean;
  secret?: boolean;
  min?: number;
  max?: number;
  min_length?: number;
  max_length?: number;
  pattern?: string;
  multiline?: boolean;
  enum?: string[];
}

export interface PluginHealth {
  healthy: boolean;
  message: string;
  checked_at?: string | null;
}

export interface PluginInfo {
  plugin_id: string;
  display_name: string;
  description: string;
  plugin_type: string;
  plugin_type_label: string;
  config_schema: Record<string, PluginSchemaField>;
  config: Record<string, unknown>;
  dependencies: Record<string, string[]>;
  capabilities: Record<string, unknown>;
  enabled: boolean;
  state: string;
  health?: PluginHealth | null;
}

export interface PluginCategory {
  type: string;
  label: string;
  plugins: PluginInfo[];
}

export interface RunInfo {
  run_id: string;
  pipeline_id: string;
  trace_id: string;
  status: string;
  orchestrator_configured: string;
  orchestrator_used: string;
  orchestrator_run_id?: string | null;
  fallback_reason?: string | null;
  current_stage?: string | null;
  human_reason?: string | null;
  error_reason?: string | null;
  started_at: string;
  finished_at?: string | null;
  input_event: EventEnvelope;
}

export interface TraceStage {
  agent: string;
  human_gate: boolean;
  status: string;
  event_id?: string | null;
  confidence?: number | null;
  latency_ms?: number | null;
}

export interface Ticket {
  ticket_id: string;
  ticket_key: string;
  trace_id: string;
  title: string;
  status: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface KnowledgeEntry {
  entry_id: string;
  title: string;
  content: string;
  category: string;
  summary?: string | null;
  root_cause?: string | null;
  source_trace_id?: string | null;
  created_at: string;
  score?: number | null;
}

export interface DeadLetter {
  id: number;
  run_id?: string | null;
  trace_id: string;
  reason: string;
  event?: EventEnvelope | null;
  created_at: string;
}

export interface TraceDetail {
  run: RunInfo;
  events: EventEnvelope[];
  ticket: Ticket | null;
  dead_letters: DeadLetter[];
  pipeline: PipelineRecord | null;
  knowledge: KnowledgeEntry[];
  stages: TraceStage[];
  available_actions: string[];
  metrics: {
    confidence?: number | null;
    tat_seconds: number;
    tat_source?: string | null;
    model_usage: Record<string, number>;
  };
}

export interface TraceSummary {
  run_id: string;
  trace_id: string;
  pipeline_id: string;
  case_id?: string | null;
  title?: string | null;
  job_name?: string | null;
  status: string;
  current_stage?: string | null;
  orchestrator_configured: string;
  orchestrator_used: string;
  fallback_reason?: string | null;
  confidence?: number | null;
  category?: string | null;
  ticket_key?: string | null;
  tat_seconds: number;
  tat_source?: string | null;
  human_reason?: string | null;
  error_reason?: string | null;
  started_at: string;
  finished_at?: string | null;
}

export interface DashboardData {
  timezone: string;
  today_start?: string;
  stats: {
    pending_failures: number;
    waiting_human: number;
    running: number;
    completed: number;
    rejected: number;
    failed: number;
    avg_tat_seconds: number;
    avg_tat_source?: string | null;
    ticket_count: number;
    knowledge_count: number;
    total_today: number;
  };
  baselines: {
    human_tat_minutes: number;
    demo_tat_minutes: number;
    source?: string;
  };
  recent_traces: TraceSummary[];
}

export interface ExperimentBaseline {
  name: string;
  model_loc?: string | null;
  tat_minutes: number;
  cost_per_ticket?: number | null;
  confidence?: number | null;
  source: string;
}

export interface ExperimentSummary {
  baselines: ExperimentBaseline[];
  computed: {
    run_count: number;
    avg_tat_seconds?: number | null;
    avg_tat_source?: string | null;
    avg_confidence?: number | null;
    model_usage: Record<string, number>;
    knowledge_stats: {
      kb_hit: {
        count: number;
        avg_confidence?: number | null;
        avg_triage_latency_ms?: number | null;
      };
      no_kb: {
        count: number;
        avg_confidence?: number | null;
        avg_triage_latency_ms?: number | null;
      };
    };
  };
}

export interface DemoCase {
  case_id: string;
  title: string;
  job_name: string;
  build_number: number;
  repository: string;
  branch: string;
  commit: string;
  stage: string;
  log_excerpt: string;
  demo_group: string;
}

export interface PushEventResult {
  run_id: string;
  trace_id: string;
  case_id: string;
  orchestrator_configured: string;
  orchestrator_effective: string;
  fallback_reason?: string | null;
  event: EventEnvelope;
}
