import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Icon } from "../Icon";
import { Badge, SectionCard, Spinner } from "../components/Ui";
import { useToast } from "../Toast";
import type { PipelineDefinition, PipelineStage } from "../types";
import { AGENT_LABELS, AGENT_SUBTITLES, orchestratorLabel } from "../utils";

type AgentNodeData = {
  label: string;
  subtitle: string;
  agent: string;
  gate: boolean;
};

type AgentNode = Node<AgentNodeData, "agent">;

const nodeTypes = { agent: AgentFlowNode };

function AgentFlowNode({ data, selected }: NodeProps<AgentNode>) {
  return (
    <div className={`flow-node${data.gate ? " flow-node-gate" : ""}${selected ? " selected" : ""}`}>
      <Handle type="target" position={Position.Left} id="target-left" className="flow-handle" />
      <Handle type="target" position={Position.Right} id="target-right" className="flow-handle" />
      <Handle type="target" position={Position.Top} id="target-top" className="flow-handle" />
      <div className="flow-node-icon">
        <Icon name={data.gate ? "shield" : "cpu"} size={17} />
      </div>
      <div>
        <strong>{data.label}</strong>
        <span>{data.subtitle}</span>
      </div>
      {data.gate ? <span className="flow-gate">人工卡点</span> : null}
      <Handle type="source" position={Position.Right} id="source-right" className="flow-handle" />
      <Handle type="source" position={Position.Left} id="source-left" className="flow-handle" />
      <Handle type="source" position={Position.Bottom} id="source-bottom" className="flow-handle" />
    </div>
  );
}

function buildNodes(stages: PipelineStage[]): AgentNode[] {
  return stages.map((stage, index) => {
    // 6 个节点按蛇形两行排布,避免单行过宽导致 fitView 缩放过小。
    const row = Math.floor(index / 3);
    const positionInRow = index % 3;
    const column = row % 2 === 0 ? positionInRow : 2 - positionInRow;
    return {
      id: stage.agent,
      type: "agent" as const,
      position: { x: column * 260, y: row * 170 + 40 },
      data: {
        label: AGENT_LABELS[stage.agent] ?? stage.agent,
        subtitle: AGENT_SUBTITLES[stage.agent] ?? stage.agent,
        agent: stage.agent,
        gate: Boolean(stage.human_gate),
      },
    };
  });
}

function buildEdges(stages: PipelineStage[]): Edge[] {
  return stages.slice(1).map((stage, index) => {
    const previous = stages[index];
    const previousRow = Math.floor(index / 3);
    const currentRow = Math.floor((index + 1) / 3);
    let sourceHandle = "source-right";
    let targetHandle = "target-left";
    if (previousRow !== currentRow) {
      sourceHandle = "source-bottom";
      targetHandle = "target-top";
    } else if (currentRow > 0) {
      // 第二行是蛇形回折,连线从右向左。
      sourceHandle = "source-left";
      targetHandle = "target-right";
    }
    return {
      id: `edge-${previous.agent}-${stage.agent}`,
      source: previous.agent,
      target: stage.agent,
      sourceHandle,
      targetHandle,
      animated: true,
      style: { stroke: "#94a3b8", strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
    };
  });
}

export function CanvasPage() {
  const [definition, setDefinition] = useState<PipelineDefinition | null>(null);
  const [orchestrator, setOrchestrator] = useState("airflow_orchestrator");
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<AgentNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { showToast } = useToast();
  const navigate = useNavigate();

  const applyDefinition = useCallback(
    (next: PipelineDefinition) => {
      setDefinition(next);
      setOrchestrator(next.orchestrator);
      setNodes(buildNodes(next.stages));
      setEdges(buildEdges(next.stages));
      setSelectedAgent(next.stages[0]?.agent ?? null);
    },
    [setEdges, setNodes],
  );

  useEffect(() => {
    api
      .pipelines()
      .then((result) => {
        const record = result.items[0];
        if (record) applyDefinition(record.definition);
        else setError("尚未配置流水线模板");
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "加载流水线失败"))
      .finally(() => setLoading(false));
  }, [applyDefinition]);

  const selectedStage = useMemo(
    () => definition?.stages.find((stage) => stage.agent === selectedAgent) ?? null,
    [definition, selectedAgent],
  );

  const resetLayout = () => {
    if (!definition) return;
    setNodes(buildNodes(definition.stages));
    setEdges(buildEdges(definition.stages));
    showToast("画布布局已重置", "info");
  };

  const updateStagePrompt = (value: string) => {
    if (!definition || !selectedAgent) return;
    setDefinition({
      ...definition,
      stages: definition.stages.map((stage) =>
        stage.agent === selectedAgent
          ? { ...stage, system_prompt: value ? value : null }
          : stage,
      ),
    });
  };

  const save = async () => {
    if (!definition) return;
    setSaving(true);
    try {
      const saved = await api.savePipeline({ ...definition, orchestrator });
      applyDefinition(saved.definition);
      showToast("流水线定义已保存", "success");
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : "保存失败", "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Spinner label="加载流水线画布…" />;
  if (error) return <div className="alert alert-danger">{error}</div>;
  if (!definition) return null;

  return (
    <div className="canvas-layout">
      <section className="canvas-panel card">
        <div className="canvas-head">
          <div>
            <span className="eyebrow">PIPELINE CANVAS</span>
            <h2>{definition.pipeline_id}</h2>
            <p>6 个 IQE Agent 串行编排 · 拖拽节点调整布局</p>
          </div>
          <div className="canvas-actions">
            <button className="button button-ghost button-small" onClick={resetLayout}>
              <Icon name="refresh" size={14} />
              重置布局
            </button>
            <button
              className="button button-primary button-small"
              onClick={() => navigate("/data-sources")}
            >
              <Icon name="play" size={14} />
              推送事件
            </button>
          </div>
        </div>
        <div className="flow-wrap">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={(_, node) => setSelectedAgent(node.id)}
            fitView
            fitViewOptions={{ padding: 0.12 }}
            minZoom={0.4}
            maxZoom={1.4}
            proOptions={{ hideAttribution: false }}
          >
            <Background variant={BackgroundVariant.Dots} gap={18} size={1.2} color="#cbd5e1" />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={(node) => (node.data?.gate ? "#f59e0b" : "#3b82f6")}
              maskColor="rgba(241,245,249,0.8)"
              pannable
            />
          </ReactFlow>
        </div>
      </section>

      <aside className="canvas-side">
        <SectionCard title="编排设置" subtitle="切换后会写入流水线定义">
          <label className="config-field">
            <div className="config-label">
              <span>编排引擎</span>
              <code>orchestrator</code>
            </div>
            <select
              value={orchestrator}
              onChange={(event) => setOrchestrator(event.target.value)}
            >
              <option value="airflow_orchestrator">Airflow Orchestrator</option>
              <option value="memory_orchestrator">内置编排引擎</option>
            </select>
            <span className="field-hint">
              当前保存值:{orchestratorLabel(orchestrator)}。Airflow 不可用时运行态会自动降级。
            </span>
          </label>
          <div className="canvas-save-row">
            <button className="button button-primary" onClick={save} disabled={saving}>
              <Icon name="check" size={15} />
              {saving ? "保存中…" : "保存流水线定义"}
            </button>
          </div>
        </SectionCard>

        <SectionCard title="阶段清单" subtitle="点击节点查看配置">
          <div className="stage-list">
            {definition.stages.map((stage, index) => (
              <button
                key={stage.agent}
                className={`stage-list-item${selectedAgent === stage.agent ? " active" : ""}`}
                onClick={() => setSelectedAgent(stage.agent)}
              >
                <span className="stage-index">{index + 1}</span>
                <span className="stage-name">
                  <strong>{AGENT_LABELS[stage.agent] ?? stage.agent}</strong>
                  <small>{stage.agent}</small>
                </span>
                {stage.system_prompt ? <Badge tone="info">Prompt</Badge> : null}
                {stage.human_gate ? <Badge tone="warning">人工</Badge> : null}
              </button>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="阶段配置" subtitle={selectedStage?.agent ?? "选择一个阶段"}>
          {selectedStage ? (
            <>
              <div className="stage-detail">
              <div>
                <span>LLM 提供商</span>
                <strong>{selectedStage.llm_provider ?? "—"}</strong>
              </div>
              <div>
                <span>知识库</span>
                <strong>{selectedStage.knowledge_base ?? "—"}</strong>
              </div>
              <div>
                <span>工具</span>
                <strong>{selectedStage.tool ?? "—"}</strong>
              </div>
              <div>
                <span>人工卡点</span>
                <strong>{selectedStage.human_gate ? "是" : "否"}</strong>
              </div>
              {selectedStage.input_source ? (
                <div>
                  <span>输入源</span>
                  <strong>{selectedStage.input_source}</strong>
                </div>
              ) : null}
            </div>
            <label className="config-field stage-prompt-field">
              <div className="config-label">
                <span>System Prompt</span>
                <code>system_prompt</code>
              </div>
              <textarea
                value={selectedStage.system_prompt ?? ""}
                onChange={(event) => updateStagePrompt(event.target.value)}
                rows={10}
                maxLength={12000}
                placeholder="留空使用 Agent 插件配置中的默认 Prompt"
              />
              <span className="field-hint">
                阶段级覆盖,保存流水线后生效;留空表示使用插件配置。
              </span>
              {selectedStage.system_prompt ? (
                <button
                  type="button"
                  className="button button-ghost button-small"
                  onClick={() => updateStagePrompt("")}
                >
                  清除阶段覆盖
                </button>
              ) : null}
            </label>
            </>
          ) : (
            <p className="muted">点击画布节点或阶段清单查看配置。</p>
          )}
        </SectionCard>

        <div className="footnote">
          文档 4.2 模板保留 Airflow + Qoder CN 配置;实际运行按文档 7.4 自动降级。
          画布位置不写入流水线定义(【已确认 Q20】)。
        </div>
      </aside>
    </div>
  );
}
