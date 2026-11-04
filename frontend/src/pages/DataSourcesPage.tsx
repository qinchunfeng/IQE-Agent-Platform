import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Icon } from "../Icon";
import { Badge, EmptyState, SectionCard, Spinner } from "../components/Ui";
import { useToast } from "../Toast";
import type { AirflowDag, DemoCase, PluginInfo } from "../types";
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
  const [airflow, setAirflow] = useState<PluginInfo | null>(null);
  const [fileSource, setFileSource] = useState<PluginInfo | null>(null);
  const [dags, setDags] = useState<AirflowDag[]>([]);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pushing, setPushing] = useState<string | null>(null);
  const [polling, setPolling] = useState<string | null>(null);
  const [uploadName, setUploadName] = useState("external_error.log");
  const [uploadText, setUploadText] = useState("");
  const [uploading, setUploading] = useState(false);
  const navigate = useNavigate();
  const { showToast } = useToast();

  const load = useCallback(async () => {
    try {
      const [caseResult, jenkinsResult, airflowResult, fileResult] = await Promise.all([
        api.cases(),
        api.plugin("mock_jenkins").catch(() => null),
        api.plugin("airflow_input").catch(() => null),
        api.plugin("file_input").catch(() => null),
      ]);
      setCases(caseResult.items);
      setPlugin(jenkinsResult);
      setAirflow(airflowResult);
      setFileSource(fileResult);
      if (airflowResult?.enabled && airflowResult.health?.healthy) {
        const dagResult = await api.airflowDags().catch(() => ({ items: [] }));
        setDags(dagResult.items);
      } else {
        setDags([]);
      }
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

  const pollSource = async (pluginId: string) => {
    setPolling(pluginId);
    try {
      const lookback = pluginId === "airflow_input" ? 10080 : 60;
      const result = await api.pollSource(pluginId, 1, lookback);
      const item = result.items[0];
      if (item) {
        showToast(`已触发:${item.case_id ?? item.source_id}`, "success");
        navigate(`/traces/${item.trace_id}`);
      } else {
        showToast("没有发现新的失败事件", "info");
      }
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : "检查失败", "error");
    } finally {
      setPolling(null);
    }
  };

  const readFile = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > 2_000_000) {
      showToast("文件不能超过 2MB", "error");
      return;
    }
    setUploadName(file.name);
    setUploadText(await file.text());
  };

  const uploadAndTrigger = async () => {
    if (!uploadText.trim()) {
      showToast("请先选择文件或粘贴日志内容", "error");
      return;
    }
    setUploading(true);
    try {
      await api.uploadLog(uploadName, uploadText);
      const result = await api.pollSource("file_input", 1, 60);
      const item = result.items[0];
      if (item) {
        showToast("外部日志已触发流水线", "success");
        navigate(`/traces/${item.trace_id}`);
      } else {
        showToast("文件已保存,但未产生新事件", "info");
      }
      setUploadText("");
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : "上传失败", "error");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="page-stack">
      {error ? <div className="alert alert-danger">{error}</div> : null}

      <section className="source-grid">
        <div className="source-card source-card-airflow">
          <div className="source-card-head">
            <div className="source-mark">
              <Icon name="layers" size={22} />
            </div>
            <div className="source-copy">
              <h2>Airflow 实时监控</h2>
              <p>
                轮询指定 DAG 的 failed Run;DAG 列表留空时监控全部。发现失败后自动创建
                monitor_alert 并触发 Agent 流水线。
              </p>
            </div>
            <Badge tone={airflow?.enabled && airflow.health?.healthy ? "success" : "neutral"}>
              {airflow?.enabled ? (airflow.health?.healthy ? "已连接" : "不可用") : "已禁用"}
            </Badge>
          </div>
          <div className="source-health">
            {airflow?.health?.message ?? "尚未配置 Airflow"}
            {dags.length ? <span> · 发现 {dags.length} 个 DAG</span> : null}
          </div>
          {dags.length ? (
            <div className="dag-chips">
              {dags.slice(0, 10).map((dag) => (
                <span className="dag-chip" key={dag.dag_id}>
                  {dag.dag_id}
                  {dag.is_paused ? <em>已暂停</em> : null}
                </span>
              ))}
            </div>
          ) : null}
          <div className="source-actions">
            <button
              className="button button-primary button-small"
              onClick={() => pollSource("airflow_input")}
              disabled={polling !== null || !airflow?.enabled}
            >
              <Icon name="refresh" size={14} />
              {polling === "airflow_input" ? "检查中…" : "立即检查(回看 7 天)"}
            </button>
            <button
              className="button button-ghost button-small"
              onClick={() => navigate("/plugins")}
            >
              配置 Airflow
            </button>
          </div>
        </div>

        <div className="source-card source-card-file">
          <div className="source-card-head">
            <div className="source-mark source-mark-file">
              <Icon name="data" size={22} />
            </div>
            <div className="source-copy">
              <h2>外部运行/错误日志</h2>
              <p>
                上传 .log/.txt/.json 文件,平台读取后生成事件;原始文件只保存在本机
                data/input_files 目录。
              </p>
            </div>
            <Badge tone={fileSource?.enabled ? "success" : "neutral"}>
              {fileSource?.enabled ? "已启用" : "已禁用"}
            </Badge>
          </div>
          <div className="file-upload-row">
            <input
              type="file"
              accept=".log,.txt,.json,.md,.out"
              onChange={(event) => readFile(event.target.files?.[0])}
            />
            <input
              value={uploadName}
              onChange={(event) => setUploadName(event.target.value)}
              placeholder="文件名"
            />
          </div>
          <textarea
            className="log-textarea"
            rows={4}
            value={uploadText}
            onChange={(event) => setUploadText(event.target.value)}
            placeholder="也可以直接粘贴错误日志内容…"
          />
          <div className="source-actions">
            <button
              className="button button-primary button-small"
              onClick={uploadAndTrigger}
              disabled={uploading || !fileSource?.enabled}
            >
              <Icon name="check" size={14} />
              {uploading ? "触发中…" : "上传并触发"}
            </button>
            <button
              className="button button-ghost button-small"
              onClick={() => pollSource("file_input")}
              disabled={polling !== null || !fileSource?.enabled}
            >
              扫描目录
            </button>
          </div>
        </div>
      </section>

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
