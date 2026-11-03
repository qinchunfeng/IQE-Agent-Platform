import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Icon } from "../Icon";
import { Badge, EmptyState, SectionCard, Spinner } from "../components/Ui";
import { useToast } from "../Toast";
import type { DemoCase, PluginInfo } from "../types";
import { GROUP_LABELS } from "../utils";

const FILTERS = [
  { key: "all", label: "全部" },
  { key: "product_bug", label: "真 Bug" },
  { key: "flaky", label: "Flaky" },
  { key: "environment", label: "环境问题" },
  { key: "driver_compatibility", label: "驱动兼容" },
  { key: "low_confidence", label: "低置信度" },
];

const SCENES = [
  {
    title: "场景 1 · 端到端自动化",
    description: "推送真 Bug 案例,自动完成 6 个 Agent 流转并创建工单。",
    caseId: "IQE-CASE-001",
    label: "推送默认案例",
    tone: "blue" as const,
  },
  {
    title: "场景 2 · 人工卡点",
    description: "推送置信度 0.6 的低置信度案例,在 Reviewer 节点暂停并等待审批。",
    caseId: "IQE-CASE-019",
    label: "推送低置信度案例",
    tone: "amber" as const,
  },
  {
    title: "场景 3 · 知识库加速(A)",
    description: "推送驱动兼容案例,在 Trace 中标记入库,再推送相似案例 B。",
    caseId: "IQE-CASE-017",
    label: "推送案例 A",
    tone: "violet" as const,
  },
  {
    title: "场景 3 · 知识库加速(B)",
    description: "案例 A 入库后再推送 B,观察 Triage 置信度 0.75 → 0.92、耗时 3 min → 30 s。",
    caseId: "IQE-CASE-018",
    label: "推送相似案例 B",
    tone: "green" as const,
  },
];

export function DataSourcesPage() {
  const [cases, setCases] = useState<DemoCase[]>([]);
  const [plugin, setPlugin] = useState<PluginInfo | null>(null);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pushing, setPushing] = useState<string | null>(null);
  const navigate = useNavigate();
  const { showToast } = useToast();

  const load = useCallback(async () => {
    try {
      const [caseResult, pluginResult] = await Promise.all([
        api.cases(),
        api.plugin("mock_jenkins").catch(() => null),
      ]);
      setCases(caseResult.items);
      setPlugin(pluginResult);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "加载数据源失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(
    () => (filter === "all" ? cases : cases.filter((item) => item.demo_group === filter)),
    [cases, filter],
  );

  const push = async (caseId: string) => {
    setPushing(caseId);
    try {
      const result = await api.pushCase(caseId);
      showToast(`事件已推送:${caseId}`, "success");
      navigate(`/traces/${result.trace_id}`);
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : "推送失败", "error");
    } finally {
      setPushing(null);
    }
  };

  return (
    <div className="page-stack">
      {error ? <div className="alert alert-danger">{error}</div> : null}

      <section className="source-banner">
        <div className="source-mark">
          <Icon name="data" size={26} />
        </div>
        <div className="source-copy">
          <h2>Mock Jenkins 输入源</h2>
          <p>
            文档 7.4:无真实 Jenkins 环境时使用 Mock Jenkins。选择预置案例即可模拟一次 CI 失败,
            事件将按文档 3.1 标准信封进入平台。
          </p>
        </div>
        <div className="source-status">
          <Badge tone={plugin?.enabled ? "success" : "danger"}>
            {plugin?.enabled ? "已启用" : "已禁用"}
          </Badge>
          <span className="muted">
            {plugin?.health?.message === "ok"
              ? "健康"
              : plugin?.health?.message ?? "健康状态未知"}
          </span>
        </div>
      </section>

      <div className="scene-grid">
        {SCENES.map((scene) => (
          <div className={`scene-card scene-${scene.tone}`} key={scene.title}>
            <div className="scene-top">
              <h3>{scene.title}</h3>
              <Badge tone={scene.tone === "blue" ? "info" : scene.tone === "amber" ? "warning" : "success"}>
                {scene.caseId}
              </Badge>
            </div>
            <p>{scene.description}</p>
            <button
              className="button button-small"
              onClick={() => push(scene.caseId)}
              disabled={pushing !== null}
            >
              <Icon name="play" size={14} />
              {pushing === scene.caseId ? "推送中…" : scene.label}
            </button>
          </div>
        ))}
      </div>

      <SectionCard
        title="预置失败案例"
        subtitle={`共 ${cases.length} 个案例,覆盖 flaky、环境、真 Bug、驱动兼容与低置信度`}
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
          <Spinner label="加载案例…" />
        ) : filtered.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>案例 ID</th>
                  <th>标题</th>
                  <th>Job / Build</th>
                  <th>分组</th>
                  <th>日志摘要</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => (
                  <tr key={item.case_id}>
                    <td className="mono">{item.case_id}</td>
                    <td>
                      <div className="cell-title">{item.title}</div>
                      <div className="cell-sub">{item.repository}</div>
                    </td>
                    <td>
                      <div>{item.job_name}</div>
                      <div className="cell-sub">#{item.build_number}</div>
                    </td>
                    <td>
                      <Badge tone={item.demo_group === "low_confidence" ? "warning" : "info"}>
                        {GROUP_LABELS[item.demo_group] ?? item.demo_group}
                      </Badge>
                    </td>
                    <td className="log-cell" title={item.log_excerpt}>
                      {item.log_excerpt}
                    </td>
                    <td>
                      <button
                        className="button button-ghost button-small"
                        onClick={() => push(item.case_id)}
                        disabled={pushing !== null}
                      >
                        {pushing === item.case_id ? "推送中…" : "推送"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="没有匹配的案例" description="尝试切换分组筛选。" />
        )}
      </SectionCard>
    </div>
  );
}
