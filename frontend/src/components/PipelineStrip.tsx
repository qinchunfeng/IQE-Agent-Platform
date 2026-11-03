import { AGENT_LABELS, AGENT_SUBTITLES, statusLabel } from "../utils";

export interface PipelineStripStage {
  agent: string;
  status: string;
  human_gate?: boolean;
  confidence?: number | null;
}

const DEFAULT_STAGES: PipelineStripStage[] = [
  { agent: "monitor_agent", status: "pending" },
  { agent: "triage_agent", status: "pending" },
  { agent: "reproduction_agent", status: "pending" },
  { agent: "ticket_agent", status: "pending" },
  { agent: "reviewer_agent", status: "pending", human_gate: true },
  { agent: "reporting_agent", status: "pending" },
];

export function PipelineStrip({
  stages,
  compact = false,
}: {
  stages?: PipelineStripStage[];
  compact?: boolean;
}) {
  const data = stages && stages.length ? stages : DEFAULT_STAGES;
  return (
    <div className={`pipeline-strip${compact ? " compact" : ""}`}>
      {data.map((stage, index) => (
        <div className="pipeline-segment" key={stage.agent}>
          <div
            className={`pipeline-node node-${stage.status}${stage.human_gate ? " has-gate" : ""}`}
            title={statusLabel(stage.status)}
          >
            <div className="pipeline-index">{index + 1}</div>
            <div className="pipeline-text">
              <div className="pipeline-name">{AGENT_LABELS[stage.agent] ?? stage.agent}</div>
              <div className="pipeline-sub">{AGENT_SUBTITLES[stage.agent] ?? stage.agent}</div>
            </div>
            {stage.human_gate ? <span className="gate-mark">H</span> : null}
            <span className="pipeline-dot" />
          </div>
          {index < data.length - 1 ? <div className="pipeline-link" /> : null}
        </div>
      ))}
    </div>
  );
}
