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
  selectedIndex = null,
  onSelectStage,
}: {
  stages?: PipelineStripStage[];
  compact?: boolean;
  selectedIndex?: number | null;
  onSelectStage?: (index: number) => void;
}) {
  const data = stages && stages.length ? stages : DEFAULT_STAGES;
  const interactive = Boolean(onSelectStage);

  return (
    <div className={`pipeline-strip${compact ? " compact" : ""}`}>
      {data.map((stage, index) => {
        const active = stage.status === "running";
        return (
          <div className="pipeline-segment" key={`${stage.agent}-${index}`}>
            <div
              className={`pipeline-node node-${stage.status}${stage.human_gate ? " has-gate" : ""}${
                interactive ? " is-clickable" : ""
              }${active ? " is-active" : ""}${selectedIndex === index ? " is-selected" : ""}`}
              title={statusLabel(stage.status)}
              role={interactive ? "button" : undefined}
              tabIndex={interactive ? 0 : undefined}
              aria-pressed={interactive ? selectedIndex === index : undefined}
              onClick={interactive ? () => onSelectStage?.(index) : undefined}
              onKeyDown={
                interactive
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelectStage?.(index);
                      }
                    }
                  : undefined
              }
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
        );
      })}
    </div>
  );
}
