import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import { Icon } from "../Icon";
import { Badge, EmptyState, SectionCard, Spinner, StatCard } from "../components/Ui";
import type { ExperimentSummary } from "../types";
import { formatDuration, formatLatency, formatPercent, tatSourceLabel } from "../utils";

const COLORS = {
  cloud: "#2563eb",
  local: "#8b5cf6",
  human: "#94a3b8",
  kb: "#16a34a",
  noKb: "#f59e0b",
};

export function ExperimentsPage() {
  const [data, setData] = useState<ExperimentSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .experiments()
      .then(setData)
      .catch((cause) => setError(cause instanceof Error ? cause.message : "加载实验数据失败"));
  }, []);

  if (error) return <div className="alert alert-danger">{error}</div>;
  if (!data) return <Spinner label="加载实验数据…" />;

  const cloud = data.baselines.find((item) => item.model_loc === "cloud_qoder_cn");
  const local = data.baselines.find((item) => item.model_loc === "local_strix_halo");
  const human = data.baselines.find((item) => item.name.includes("人工"));
  const kb = data.computed.knowledge_stats.kb_hit;
  const noKb = data.computed.knowledge_stats.no_kb;

  const tatData = [
    { name: "人工处理", minutes: human?.tat_minutes ?? 45, fill: COLORS.human },
    { name: "Qoder CN Cloud", minutes: cloud?.tat_minutes ?? 8, fill: COLORS.cloud },
    { name: "Mock Local", minutes: local?.tat_minutes ?? 12, fill: COLORS.local },
  ];
  const costData = [
    { name: "Qoder CN Cloud", cost: cloud?.cost_per_ticket ?? 2.5, fill: COLORS.cloud },
    { name: "Mock Local", cost: local?.cost_per_ticket ?? 0.3, fill: COLORS.local },
  ];
  const confidenceData = [
    { name: "Qoder CN Cloud", confidence: (cloud?.confidence ?? 0.88) * 100, fill: COLORS.cloud },
    { name: "Mock Local", confidence: (local?.confidence ?? 0.85) * 100, fill: COLORS.local },
    {
      name: "平台实测均值",
      confidence: (data.computed.avg_confidence ?? 0) * 100,
      fill: "#0f766e",
    },
  ];
  const knowledgeData = [
    {
      name: "未命中知识库",
      confidence: (noKb.avg_confidence ?? 0) * 100,
      latency: (noKb.avg_triage_latency_ms ?? 0) / 60_000,
      fill: COLORS.noKb,
    },
    {
      name: "命中知识库",
      confidence: (kb.avg_confidence ?? 0) * 100,
      latency: (kb.avg_triage_latency_ms ?? 0) / 60_000,
      fill: COLORS.kb,
    },
  ];

  return (
    <div className="page-stack">
      <div className="alert alert-info inline-alert">
        <Icon name="alert" size={16} />
        <span>
          场景 5 的 TAT / 成本 / 置信度来自文档基线(标注“文档基线”);Mock 模式下业务耗时按文档场景模拟,
          不作为真实墙钟指标【已确认 Q12】。
        </span>
      </div>

      <div className="comparison-grid">
        <div className="comparison-card comparison-cloud">
          <div className="comparison-head">
            <Badge tone="info">Qoder CN Cloud</Badge>
            <span>文档基线</span>
          </div>
          <div className="comparison-value">{cloud?.tat_minutes ?? 8} min</div>
          <div className="comparison-label">平均 TAT</div>
          <div className="comparison-facts">
            <span>单票成本 ¥{cloud?.cost_per_ticket ?? 2.5}</span>
            <span>置信度 {formatPercent(cloud?.confidence ?? 0.88)}</span>
          </div>
        </div>
        <div className="comparison-card comparison-local">
          <div className="comparison-head">
            <Badge tone="success">Mock Local</Badge>
            <span>模拟 Strix Halo</span>
          </div>
          <div className="comparison-value">{local?.tat_minutes ?? 12} min</div>
          <div className="comparison-label">平均 TAT</div>
          <div className="comparison-facts">
            <span>单票成本 ¥{local?.cost_per_ticket ?? 0.3}</span>
            <span>置信度 {formatPercent(local?.confidence ?? 0.85)}</span>
          </div>
        </div>
        <div className="comparison-card comparison-human">
          <div className="comparison-head">
            <Badge tone="neutral">人工处理</Badge>
            <span>文档基线</span>
          </div>
          <div className="comparison-value">{human?.tat_minutes ?? 45} min</div>
          <div className="comparison-label">平均 TAT</div>
          <div className="comparison-facts">
            <span>混合策略可降低成本 70%</span>
            <span>质量损失 &lt;5%</span>
          </div>
        </div>
      </div>

      <div className="stats-grid stats-grid-4">
        <StatCard
          title="累计实验流水线"
          value={data.computed.run_count}
          hint="Mock 与真实 LLM 均计入"
          icon="traces"
          accent="blue"
        />
        <StatCard
          title="平均 TAT"
          value={formatDuration(data.computed.avg_tat_seconds ?? 0)}
          hint={`来源:${tatSourceLabel(data.computed.avg_tat_source)}`}
          icon="clock"
          accent="amber"
        />
        <StatCard
          title="实测平均置信度"
          value={formatPercent(data.computed.avg_confidence ?? 0)}
          hint="以 Triage 输出为准"
          icon="shield"
          accent="green"
        />
        <StatCard
          title="知识库命中次数"
          value={kb.count}
          hint={`未命中 ${noKb.count} 次`}
          icon="knowledge"
          accent="violet"
        />
      </div>

      <div className="chart-grid">
        <SectionCard title="TAT 对比" subtitle="人工 vs 云端 vs 本地(分钟,文档基线)">
          <div className="chart-box">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={tatData} margin={{ top: 16, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip formatter={(value) => [`${value} min`, "TAT"]} />
                <Bar dataKey="minutes" radius={[8, 8, 0, 0]}>
                  {tatData.map((item) => (
                    <Cell key={item.name} fill={item.fill} />
                  ))}
                  <LabelList dataKey="minutes" position="top" fontSize={12} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="单票成本" subtitle="¥ / ticket(文档基线)">
          <div className="chart-box">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={costData} margin={{ top: 16, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip formatter={(value) => [`¥${value}`, "单票成本"]} />
                <Bar dataKey="cost" radius={[8, 8, 0, 0]}>
                  {costData.map((item) => (
                    <Cell key={item.name} fill={item.fill} />
                  ))}
                  <LabelList dataKey="cost" position="top" fontSize={12} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="置信度对比" subtitle="百分比,文档基线 + 平台实测均值">
          <div className="chart-box">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={confidenceData} margin={{ top: 16, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(value) => [`${Number(value).toFixed(0)}%`, "置信度"]} />
                <Bar dataKey="confidence" radius={[8, 8, 0, 0]}>
                  {confidenceData.map((item) => (
                    <Cell key={item.name} fill={item.fill} />
                  ))}
                  <LabelList dataKey="confidence" position="top" fontSize={12} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard
          title="知识库效果"
          subtitle={`命中 ${kb.count} 次 vs 未命中 ${noKb.count} 次`}
        >
          {kb.count === 0 && noKb.count === 0 ? (
            <EmptyState
              title="暂无知识库对比数据"
              description="完成场景 3:先推送案例 A 并标记入库,再推送案例 B。"
            />
          ) : (
            <div className="kb-chart-stack">
              <div className="chart-box chart-box-small">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={knowledgeData} margin={{ top: 16, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                    <Tooltip formatter={(value) => [`${Number(value).toFixed(0)}%`, "置信度"]} />
                    <Bar dataKey="confidence" radius={[8, 8, 0, 0]}>
                      {knowledgeData.map((item) => (
                        <Cell key={item.name} fill={item.fill} />
                      ))}
                      <LabelList dataKey="confidence" position="top" fontSize={12} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="kb-facts">
                <span>
                  Triage 平均耗时:未命中{" "}
                  <strong>{formatLatency(noKb.avg_triage_latency_ms)}</strong>,命中{" "}
                  <strong>{formatLatency(kb.avg_triage_latency_ms)}</strong>
                </span>
                <span>
                  平均置信度:未命中 <strong>{formatPercent(noKb.avg_confidence)}</strong>,命中{" "}
                  <strong>{formatPercent(kb.avg_confidence)}</strong>
                </span>
              </div>
            </div>
          )}
        </SectionCard>
      </div>

      <SectionCard title="模型调用分布" subtitle="来自全部 Trace 的 model_info.model_loc">
        <div className="model-usage">
          {Object.entries(data.computed.model_usage).length ? (
            Object.entries(data.computed.model_usage).map(([loc, count]) => (
              <div className="model-usage-item" key={loc}>
                <span>{loc}</span>
                <strong>{count}</strong>
                <div className="model-usage-bar">
                  <span
                    style={{
                      width: `${Math.min(
                        100,
                        (count /
                          Math.max(
                            1,
                            Object.values(data.computed.model_usage).reduce((sum, value) => sum + value, 0),
                          )) *
                          100,
                      )}%`,
                    }}
                  />
                </div>
              </div>
            ))
          ) : (
            <EmptyState title="暂无模型调用数据" />
          )}
        </div>
      </SectionCard>
    </div>
  );
}
