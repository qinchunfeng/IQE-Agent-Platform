import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Icon } from "../Icon";
import { PipelineStrip } from "../components/PipelineStrip";
import {
  Badge,
  ConfidenceMeter,
  EmptyState,
  SectionCard,
  Spinner,
  StatCard,
  StatusBadge,
} from "../components/Ui";
import { useToast } from "../Toast";
import type { DashboardData } from "../types";
import {
  formatDateTime,
  formatDuration,
  orchestratorLabel,
  shortId,
  tatSourceLabel,
} from "../utils";

const DEFAULT_CASE = "IQE-CASE-001";

export function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pushing, setPushing] = useState(false);
  const navigate = useNavigate();
  const { showToast } = useToast();

  const load = useCallback(async () => {
    try {
      const result = await api.dashboard();
      setData(result);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "加载仪表盘失败");
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 3000);
    return () => window.clearInterval(timer);
  }, [load]);

  const pushDefault = async () => {
    setPushing(true);
    try {
      const result = await api.pushCase(DEFAULT_CASE);
      showToast("模拟 CI 失败事件已推送,正在进入流水线", "success");
      navigate(`/traces/${result.trace_id}`);
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : "推送失败", "error");
    } finally {
      setPushing(false);
    }
  };

  if (!data && !error) {
    return <Spinner label="加载仪表盘…" />;
  }

  const stats = data?.stats;
  const latest = data?.recent_traces[0];

  return (
    <div className="page-stack">
      {error ? <div className="alert alert-danger">{error}</div> : null}

      <section className="hero-card">
        <div className="hero-glow" />
        <div className="hero-copy">
          <span className="eyebrow">PLUGIN-DRIVEN AUTOMATION</span>
          <h2>从 CI 失败到有效工单,一条流水线自动完成</h2>
          <p>
            Monitor → Triage → Reproduction → Ticket → Reviewer → Reporting。
            6 个 IQE Agent 串行协作,低置信度自动转人工,外部系统不可用时自动降级。
          </p>
          <div className="hero-actions">
            <button className="button button-primary" onClick={pushDefault} disabled={pushing}>
              <Icon name="play" size={16} />
              {pushing ? "推送中…" : "推送模拟 CI 失败事件"}
            </button>
            <Link className="button button-ghost" to="/data-sources">
              选择演示案例
              <Icon name="arrow" size={16} />
            </Link>
          </div>
          <div className="hero-badges">
            <span>8 类插件</span>
            <span>6 个 IQE Agent</span>
            <span>Mock 自动降级</span>
            <span>完整 Trace</span>
          </div>
        </div>
        <div className="hero-metrics">
          <div className="hero-metric">
            <span>人工处理平均</span>
            <strong>{data?.baselines.human_tat_minutes ?? 45} min</strong>
          </div>
          <div className="hero-arrow">
            <Icon name="arrow" size={22} />
          </div>
          <div className="hero-metric hero-metric-highlight">
            <span>平台演示基线</span>
            <strong>{data?.baselines.demo_tat_minutes ?? 8} min</strong>
          </div>
          <div className="hero-saving">TAT 缩短 80%</div>
          <div className="hero-source">
            基线来源:文档 6 场景 1 · 今日口径:{data?.timezone ?? "服务端本地时区"}
          </div>
        </div>
      </section>

      <div className="stats-grid">
        <StatCard
          title="今日待处理失败"
          value={stats?.pending_failures ?? 0}
          hint={`${stats?.waiting_human ?? 0} 个等待人工 · ${stats?.running ?? 0} 个运行中`}
          icon="traces"
          accent="amber"
        />
        <StatCard
          title="今日已完成"
          value={stats?.completed ?? 0}
          hint={`${stats?.rejected ?? 0} 个已驳回 · ${stats?.failed ?? 0} 个失败`}
          icon="check"
          accent="green"
        />
        <StatCard
          title="平均 TAT"
          value={formatDuration(stats?.avg_tat_seconds ?? 0)}
          hint={tatSourceLabel(stats?.avg_tat_source)}
          icon="clock"
          accent="blue"
        />
        <StatCard
          title="今日工单"
          value={stats?.ticket_count ?? 0}
          hint="Reviewer 通过后写入 Mock Jira"
          icon="ticket"
          accent="violet"
        />
        <StatCard
          title="知识库条目"
          value={stats?.knowledge_count ?? 0}
          hint="Reviewer 阶段可标记入库"
          icon="knowledge"
          accent="rose"
        />
      </div>

      <SectionCard
        title="平台流水线"
        subtitle="文档 4.2 IQE Validation v1 · 6 个 Agent 串行执行"
        action={
          <Link className="text-link" to="/canvas">
            打开画布 <Icon name="arrow" size={14} />
          </Link>
        }
      >
        <PipelineStrip />
      </SectionCard>

      <div className="dashboard-columns">
        <SectionCard
          title="最近 Trace"
          subtitle="点击任意记录查看完整事件链"
          action={
            <Link className="text-link" to="/traces">
              全部 Trace <Icon name="arrow" size={14} />
            </Link>
          }
        >
          {data?.recent_traces.length ? (
            <div className="table-wrap">
              <table className="data-table clickable">
                <thead>
                  <tr>
                    <th>案例</th>
                    <th>状态</th>
                    <th>置信度</th>
                    <th>分类</th>
                    <th>TAT</th>
                    <th>工单</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_traces.map((trace) => (
                    <tr
                      key={trace.trace_id}
                      onClick={() => navigate(`/traces/${trace.trace_id}`)}
                    >
                      <td>
                        <div className="cell-title">{trace.title ?? trace.case_id}</div>
                        <div className="cell-sub">{shortId(trace.trace_id, 10)}</div>
                      </td>
                      <td>
                        <StatusBadge status={trace.status} />
                      </td>
                      <td>
                        <ConfidenceMeter value={trace.confidence} />
                      </td>
                      <td>
                        {trace.category ? <Badge tone="info">{trace.category}</Badge> : "—"}
                      </td>
                      <td>
                        <div>{formatDuration(trace.tat_seconds)}</div>
                        <div className="cell-sub">{tatSourceLabel(trace.tat_source)}</div>
                      </td>
                      <td>{trace.ticket_key ?? "—"}</td>
                      <td className="cell-sub">{formatDateTime(trace.started_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="今日待处理失败:0"
              description="推送一个模拟 CI 失败事件,即可看到 6 个 Agent 自动流转。"
              action={
                <button className="button button-primary" onClick={pushDefault} disabled={pushing}>
                  <Icon name="play" size={16} />
                  推送模拟事件
                </button>
              }
            />
          )}
        </SectionCard>

        <div className="side-stack">
          <SectionCard title="当前运行态" subtitle="配置编排器 vs 实际编排器">
            {latest ? (
              <div className="run-state">
                <div className="run-state-row">
                  <span>最新状态</span>
                  <StatusBadge status={latest.status} />
                </div>
                <div className="run-state-row">
                  <span>配置编排器</span>
                  <strong>{orchestratorLabel(latest.orchestrator_configured)}</strong>
                </div>
                <div className="run-state-row">
                  <span>实际编排器</span>
                  <strong>{orchestratorLabel(latest.orchestrator_used)}</strong>
                </div>
                {latest.fallback_reason ? (
                  <div className="fallback-note">
                    <Icon name="alert" size={14} />
                    <span>{latest.fallback_reason}</span>
                  </div>
                ) : null}
                <div className="run-state-row">
                  <span>最近事件</span>
                  <span className="muted">{latest.title ?? latest.case_id}</span>
                </div>
              </div>
            ) : (
              <p className="muted">
                等待首个事件。Airflow / Qoder CN 默认不可用时,平台会自动降级并照常运行。
              </p>
            )}
          </SectionCard>

          <SectionCard title="演示路径" subtitle="5 个场景的核心入口">
            <div className="demo-links">
              <Link to="/data-sources" className="demo-link">
                <span className="demo-link-index">1</span>
                <div>
                  <strong>端到端自动化</strong>
                  <span>推送事件,自动生成工单</span>
                </div>
                <Icon name="arrow" size={14} />
              </Link>
              <Link to="/data-sources" className="demo-link">
                <span className="demo-link-index">2</span>
                <div>
                  <strong>人工卡点</strong>
                  <span>0.6 低置信度案例,驳回/批准</span>
                </div>
                <Icon name="arrow" size={14} />
              </Link>
              <Link to="/data-sources" className="demo-link">
                <span className="demo-link-index">3</span>
                <div>
                  <strong>知识库加速</strong>
                  <span>入库后相似案例命中 0.92</span>
                </div>
                <Icon name="arrow" size={14} />
              </Link>
              <Link to="/experiments" className="demo-link">
                <span className="demo-link-index">4</span>
                <div>
                  <strong>成本对比</strong>
                  <span>本地 vs 云端 ROI</span>
                </div>
                <Icon name="arrow" size={14} />
              </Link>
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
