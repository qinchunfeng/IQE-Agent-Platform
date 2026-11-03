import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Icon } from "../Icon";
import {
  Badge,
  ConfidenceMeter,
  EmptyState,
  SectionCard,
  Spinner,
  StatusBadge,
} from "../components/Ui";
import type { TraceSummary } from "../types";
import {
  formatDateTime,
  formatDuration,
  isActiveRun,
  orchestratorLabel,
  shortId,
  statusLabel,
} from "../utils";

const FILTERS = [
  { key: "all", label: "全部" },
  { key: "running", label: "运行中" },
  { key: "waiting_human", label: "等待人工" },
  { key: "completed", label: "已完成" },
  { key: "rejected", label: "已驳回" },
  { key: "failed", label: "失败" },
];

export function TracesPage() {
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      const result = await api.traces(100, filter === "all" ? undefined : filter);
      setTraces(result.items);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "加载 Trace 失败");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    setLoading(true);
    load();
    const timer = window.setInterval(load, 2500);
    return () => window.clearInterval(timer);
  }, [load]);

  const activeCount = traces.filter((trace) => isActiveRun(trace.status)).length;

  return (
    <div className="page-stack">
      {error ? <div className="alert alert-danger">{error}</div> : null}

      <div className="trace-summary-row">
        <div className="trace-summary-item">
          <span>Trace 总数</span>
          <strong>{traces.length}</strong>
        </div>
        <div className="trace-summary-item">
          <span>运行中 / 待人工</span>
          <strong>{activeCount}</strong>
        </div>
        <div className="trace-summary-item">
          <span>已完成</span>
          <strong>{traces.filter((trace) => trace.status === "completed").length}</strong>
        </div>
        <div className="trace-summary-item">
          <span>已驳回 / 失败</span>
          <strong>
            {traces.filter((trace) => ["rejected", "failed"].includes(trace.status)).length}
          </strong>
        </div>
      </div>

      <SectionCard
        title="Trace 列表"
        subtitle="每次 CI 失败事件对应一个 trace_id;低置信度会停在 Reviewer"
        action={
          <div className="filter-row">
            {FILTERS.map((item) => (
              <button
                key={item.key}
                className={`chip${filter === item.key ? " active" : ""}`}
                onClick={() => setFilter(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
        }
      >
        {loading ? (
          <Spinner label="加载 Trace…" />
        ) : traces.length ? (
          <div className="table-wrap">
            <table className="data-table clickable">
              <thead>
                <tr>
                  <th>Trace / 案例</th>
                  <th>状态</th>
                  <th>当前阶段</th>
                  <th>置信度</th>
                  <th>分类</th>
                  <th>编排器</th>
                  <th>TAT</th>
                  <th>工单</th>
                  <th>开始时间</th>
                </tr>
              </thead>
              <tbody>
                {traces.map((trace) => (
                  <tr key={trace.trace_id} onClick={() => navigate(`/traces/${trace.trace_id}`)}>
                    <td>
                      <div className="cell-title">{trace.title ?? trace.case_id ?? "CI failure"}</div>
                      <div className="cell-sub mono">{shortId(trace.trace_id, 12)}</div>
                    </td>
                    <td>
                      <StatusBadge status={trace.status} />
                    </td>
                    <td>
                      {trace.current_stage ? (
                        <span className="mono small">{trace.current_stage}</span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>
                      <ConfidenceMeter value={trace.confidence} />
                    </td>
                    <td>{trace.category ? <Badge tone="info">{trace.category}</Badge> : "—"}</td>
                    <td>
                      <div>{orchestratorLabel(trace.orchestrator_used)}</div>
                      {trace.fallback_reason ? (
                        <div className="cell-sub fallback-cell">
                          <Icon name="alert" size={12} />
                          已降级
                        </div>
                      ) : null}
                    </td>
                    <td>{formatDuration(trace.tat_seconds)}</td>
                    <td>{trace.ticket_key ?? "—"}</td>
                    <td className="cell-sub">{formatDateTime(trace.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title={filter === "all" ? "还没有 Trace" : `没有${statusLabel(filter)}的 Trace`}
            description="前往数据源页面推送一个模拟 CI 失败事件。"
            action={
              <button className="button button-primary" onClick={() => navigate("/data-sources")}>
                去推送事件
              </button>
            }
          />
        )}
      </SectionCard>
    </div>
  );
}
