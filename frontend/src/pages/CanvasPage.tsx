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
import type {
  PipelineDefinition,
  PipelineSource,
  PipelineStage,
  PluginCategory,
  PluginInfo,
} from "../types";
import {
  AGENT_LABELS,
  AGENT_SUBTITLES,
  INPUT_SOURCE_LABELS,
  inputSourceLabel,
  orchestratorLabel,
} from "../utils";

type AgentNodeData = {
  label: string;
  subtitle: string;
  agent: string;
  gate: boolean;
  index: number;
};

type SourceNodeData = {
  label: string;
  pluginId: string;
  enabled: boolean;
  index: number;
};

type AgentNode = Node<AgentNodeData, "agent">;
type SourceNode = Node<SourceNodeData, "source">;
type CanvasNode = AgentNode | SourceNode;

const nodeTypes = { agent: AgentFlowNode, source: SourceFlowNode };

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
        <strong>
          {data.label}
          {data.index > 0 ? <small className="flow-node-index"> #{data.index + 1}</small> : null}
        </strong>
        <span>{data.subtitle}</span>
      </div>
      {data.gate ? <span className="flow-gate">人工卡点</span> : null}
      <Handle type="source" position={Position.Right} id="source-right" className="flow-handle" />
      <Handle type="source" position={Position.Left} id="source-left" className="flow-handle" />
      <Handle type="source" position={Position.Bottom} id="source-bottom" className="flow-handle" />
    </div>
  );
}

function SourceFlowNode({ data, selected }: NodeProps<SourceNode>) {
  return (
    <div
      className={`flow-node flow-node-source${data.enabled ? "" : " flow-node-disabled"}${selected ? " selected" : ""}`}
    >
      <div className="flow-node-icon">
        <Icon name="data" size={17} />
      </div>
      <div>
        <strong>{data.label}</strong>
        <span>{data.pluginId}</span>
      </div>
      {!data.enabled ? <span className="flow-gate">已停用</span> : null}
      <Handle type="source" position={Position.Right} id="source-right" className="flow-handle" />
    </div>
  );
}

function buildNodes(definition: PipelineDefinition): CanvasNode[] {
  const sources: SourceNode[] = definition.sources.map((source, index) => ({
    id: `source-${index}`,
    type: "source" as const,
    position: { x: -300, y: index * 120 + 40 },
    data: {
      label: source.label || INPUT_SOURCE_LABELS[source.plugin_id] || source.plugin_id,
      pluginId: source.plugin_id,
      enabled: source.enabled !== false,
      index,
    },
  }));
  const stages: AgentNode[] = definition.stages.map((stage, index) => {
    // 节点按蛇形两行排布,避免单行过宽导致 fitView 缩放过小。
    const row = Math.floor(index / 3);
    const positionInRow = index % 3;
    const column = row % 2 === 0 ? positionInRow : 2 - positionInRow;
    return {
      id: `stage-${index}`,
      type: "agent" as const,
      position: { x: column * 260, y: row * 170 + 40 },
      data: {
        label: AGENT_LABELS[stage.agent] ?? stage.agent,
        subtitle: AGENT_SUBTITLES[stage.agent] ?? stage.agent,
        agent: stage.agent,
        gate: Boolean(stage.human_gate),
        index,
      },
    };
  });
  return [...sources, ...stages];
}

function buildEdges(definition: PipelineDefinition): Edge[] {
  const edges: Edge[] = [];
  const firstStage = definition.stages[0];
  if (firstStage) {
    definition.sources.forEach((source, index) => {
      edges.push({
        id: `edge-source-${index}-${firstStage.agent}`,
        source: `source-${index}`,
        target: "stage-0",
        sourceHandle: "source-right",
        targetHandle: "target-left",
        animated: source.enabled !== false,
        style: { stroke: "#22c55e", strokeWidth: 2, strokeDasharray: "5 4" },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#22c55e" },
      });
    });
  }
  definition.stages.slice(1).forEach((_, index) => {
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
    edges.push({
      id: `edge-stage-${index}-${index + 1}`,
      source: `stage-${index}`,
      target: `stage-${index + 1}`,
      sourceHandle,
      targetHandle,
      animated: true,
      style: { stroke: "#94a3b8", strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
    });
  });
  return edges;
}

function flattenPlugins(categories: PluginCategory[], type: string): PluginInfo[] {
  return categories.find((category) => category.type === type)?.plugins ?? [];
}

export function CanvasPage() {
  const [definition, setDefinition] = useState<PipelineDefinition | null>(null);
  const [categories, setCategories] = useState<PluginCategory[]>([]);
  const [orchestrator, setOrchestrator] = useState("memory_orchestrator");
  const [selectedStageIndex, setSelectedStageIndex] = useState<number | null>(null);
  const [newAgent, setNewAgent] = useState("");
  const [newSource, setNewSource] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { showToast } = useToast();
  const navigate = useNavigate();

  const applyDefinition = useCallback(
    (next: PipelineDefinition) => {
      setDefinition(next);
      setOrchestrator(next.orchestrator);
      setNodes(buildNodes(next));
      setEdges(buildEdges(next));
      setSelectedStageIndex(next.stages.length ? 0 : null);
    },
    [setEdges, setNodes],
  );

  useEffect(() => {
    Promise.all([api.pipelines(), api.plugins(false)])
      .then(([pipelineResult, pluginResult]) => {
        const record = pipelineResult.items[0];
        if (record) applyDefinition(record.definition);
        else setError("尚未配置流水线模板");
        setCategories(pluginResult.categories);
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "加载流水线失败"))
      .finally(() => setLoading(false));
  }, [applyDefinition]);

  const agents = useMemo(() => flattenPlugins(categories, "agent"), [categories]);
  const inputSources = useMemo(() => flattenPlugins(categories, "input_source"), [categories]);
  const llmProviders = useMemo(() => flattenPlugins(categories, "llm_provider"), [categories]);
  const knowledgeBases = useMemo(
    () => flattenPlugins(categories, "knowledge_base"),
    [categories],
  );
  const tools = useMemo(() => flattenPlugins(categories, "tool"), [categories]);

  const selectedStage = useMemo(
    () => (selectedStageIndex === null ? null : definition?.stages[selectedStageIndex] ?? null),
    [definition, selectedStageIndex],
  );

  const resetLayout = () => {
    if (!definition) return;
    setNodes(buildNodes(definition));
    setEdges(buildEdges(definition));
    showToast("画布布局已重置", "info");
  };

  const patchStage = (index: number, patch: Partial<PipelineStage>) => {
    if (!definition) return;
    setDefinition({
      ...definition,
      stages: definition.stages.map((stage, stageIndex) =>
        stageIndex === index ? { ...stage, ...patch } : stage,
      ),
    });
  };

  const updateStagePrompt = (value: string) => {
    if (selectedStageIndex === null) return;
    patchStage(selectedStageIndex, { system_prompt: value ? value : null });
  };

  const addStage = () => {
    if (!definition) return;
    const agentId = newAgent || agents[0]?.plugin_id;
    if (!agentId) return;
    const template = definition.stages[0];
    const stage: PipelineStage = {
      agent: agentId,
      llm_provider: template?.llm_provider ?? "qoder_cn",
      knowledge_base: null,
      tool: null,
      human_gate: false,
    };
    const stages = [...definition.stages, stage];
    setDefinition({ ...definition, stages });
    setNodes(buildNodes({ ...definition, stages }));
    setEdges(buildEdges({ ...definition, stages }));
    setSelectedStageIndex(stages.length - 1);
    showToast(`已新增 Agent 阶段:${AGENT_LABELS[agentId] ?? agentId}`, "success");
  };

  const removeStage = (index: number) => {
    if (!definition) return;
    if (definition.stages.length <= 1) {
      showToast("流水线至少保留 1 个 Agent 阶段", "error");
      return;
    }
    const stages = definition.stages.filter((_, stageIndex) => stageIndex !== index);
    setDefinition({ ...definition, stages });
    setNodes(buildNodes({ ...definition, stages }));
    setEdges(buildEdges({ ...definition, stages }));
    setSelectedStageIndex(Math.max(0, Math.min(index, stages.length - 1)));
  };

  const moveStage = (index: number, delta: number) => {
    if (!definition) return;
    const target = index + delta;
    if (target < 0 || target >= definition.stages.length) return;
    const stages = [...definition.stages];
    [stages[index], stages[target]] = [stages[target], stages[index]];
    setDefinition({ ...definition, stages });
    setNodes(buildNodes({ ...definition, stages }));
    setEdges(buildEdges({ ...definition, stages }));
    setSelectedStageIndex(target);
  };

  const addSource = () => {
    if (!definition) return;
    const pluginId = newSource || inputSources[0]?.plugin_id;
    if (!pluginId) return;
    let index = 1;
    let sourceId = pluginId;
    while (definition.sources.some((source) => source.source_id === sourceId)) {
      index += 1;
      sourceId = `${pluginId}-${index}`;
    }
    const plugin = inputSources.find((item) => item.plugin_id === pluginId);
    const source: PipelineSource = {
      source_id: sourceId,
      plugin_id: pluginId,
      label: plugin?.display_name ?? INPUT_SOURCE_LABELS[pluginId] ?? pluginId,
      enabled: true,
    };
    const sources = [...definition.sources, source];
    setDefinition({ ...definition, sources });
    setNodes(buildNodes({ ...definition, sources }));
    setEdges(buildEdges({ ...definition, sources }));
    showToast(`已新增输入源:${source.label}`, "success");
  };

  const patchSource = (index: number, patch: Partial<PipelineSource>) => {
    if (!definition) return;
    const sources = definition.sources.map((source, sourceIndex) =>
      sourceIndex === index ? { ...source, ...patch } : source,
    );
    setDefinition({ ...definition, sources });
    setNodes(buildNodes({ ...definition, sources }));
    setEdges(buildEdges({ ...definition, sources }));
  };

  const removeSource = (index: number) => {
    if (!definition) return;
    if (definition.sources.length <= 1) {
      showToast("流水线至少保留 1 个输入源", "error");
      return;
    }
    const sources = definition.sources.filter((_, sourceIndex) => sourceIndex !== index);
    setDefinition({ ...definition, sources });
    setNodes(buildNodes({ ...definition, sources }));
    setEdges(buildEdges({ ...definition, sources }));
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
            <p>
              {definition.sources.length} 个输入源 · {definition.stages.length} 个 Agent
              阶段 · 可自定义增删
            </p>
          </div>
          <div className="canvas-actions">
            <button className="button button-ghost button-small" onClick={resetLayout}>
              <Icon name="refresh" size={14} />
              重置布局
            </button>
            <button
              className="button button-ghost button-small"
              onClick={() => navigate("/plugins")}
            >
              <Icon name="plugins" size={14} />
              插件配置
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
            onNodeClick={(_, node) => {
              if (node.type === "agent") {
                setSelectedStageIndex((node.data as AgentNodeData).index);
              }
            }}
            fitView
            fitViewOptions={{ padding: 0.12 }}
            minZoom={0.35}
            maxZoom={1.4}
            proOptions={{ hideAttribution: false }}
          >
            <Background variant={BackgroundVariant.Dots} gap={18} size={1.2} color="#cbd5e1" />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={(node) =>
                node.type === "source"
                  ? "#22c55e"
                  : (node.data as AgentNodeData)?.gate
                    ? "#f59e0b"
                    : "#3b82f6"
              }
              maskColor="rgba(241,245,249,0.8)"
              pannable
            />
          </ReactFlow>
        </div>
      </section>

      <aside className="canvas-side">
        <SectionCard title="编排设置" subtitle="Airflow 已改为输入源插件">
          <label className="config-field">
            <div className="config-label">
              <span>编排引擎</span>
              <code>orchestrator</code>
            </div>
            <select
              value={orchestrator}
              onChange={(event) => setOrchestrator(event.target.value)}
            >
              <option value="memory_orchestrator">内置编排引擎</option>
            </select>
            <span className="field-hint">
              当前:{orchestratorLabel(orchestrator)}。Airflow 由输入源插件监控,不再调度 Agent。
            </span>
          </label>
          <div className="canvas-save-row">
            <button className="button button-primary" onClick={save} disabled={saving}>
              <Icon name="check" size={15} />
              {saving ? "保存中…" : "保存流水线定义"}
            </button>
          </div>
        </SectionCard>

        <SectionCard title="输入源" subtitle="Airflow / Jenkins / 外部日志文件">
          <div className="source-list">
            {definition.sources.map((source, index) => (
              <div className="source-list-item" key={source.source_id}>
                <span className="source-dot" />
                <div className="stage-name">
                  <strong>{source.label || inputSourceLabel(source.plugin_id)}</strong>
                  <small>
                    {source.source_id} · {source.plugin_id}
                  </small>
                </div>
                <button
                  className={`mini-toggle${source.enabled !== false ? " on" : ""}`}
                  onClick={() => patchSource(index, { enabled: source.enabled === false })}
                  title={source.enabled !== false ? "停用输入源" : "启用输入源"}
                >
                  {source.enabled !== false ? "启用" : "停用"}
                </button>
                <button
                  className="icon-button"
                  onClick={() => removeSource(index)}
                  title="删除输入源"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <div className="add-row">
            <select value={newSource} onChange={(event) => setNewSource(event.target.value)}>
              <option value="">选择输入源插件…</option>
              {inputSources.map((plugin) => (
                <option key={plugin.plugin_id} value={plugin.plugin_id}>
                  {plugin.display_name}
                </option>
              ))}
            </select>
            <button className="button button-ghost button-small" onClick={addSource}>
              添加输入源
            </button>
          </div>
          <span className="field-hint">
            连接参数在“插件管理”中配置;流水线只引用插件节点。
          </span>
        </SectionCard>

        <SectionCard title="阶段清单" subtitle="可新增、删除与排序 Agent">
          <div className="stage-list">
            {definition.stages.map((stage, index) => (
              <div
                className={`stage-list-item${selectedStageIndex === index ? " active" : ""}`}
                key={`${stage.agent}-${index}`}
                onClick={() => setSelectedStageIndex(index)}
              >
                <span className="stage-index">{index + 1}</span>
                <span className="stage-name">
                  <strong>{AGENT_LABELS[stage.agent] ?? stage.agent}</strong>
                  <small>{stage.agent}</small>
                </span>
                {stage.system_prompt ? <Badge tone="info">Prompt</Badge> : null}
                {stage.human_gate ? <Badge tone="warning">人工</Badge> : null}
                <span className="stage-actions">
                  <button
                    className="icon-button"
                    title="上移"
                    onClick={(event) => {
                      event.stopPropagation();
                      moveStage(index, -1);
                    }}
                  >
                    ↑
                  </button>
                  <button
                    className="icon-button"
                    title="下移"
                    onClick={(event) => {
                      event.stopPropagation();
                      moveStage(index, 1);
                    }}
                  >
                    ↓
                  </button>
                  <button
                    className="icon-button"
                    title="删除"
                    onClick={(event) => {
                      event.stopPropagation();
                      removeStage(index);
                    }}
                  >
                    ×
                  </button>
                </span>
              </div>
            ))}
          </div>
          <div className="add-row">
            <select value={newAgent} onChange={(event) => setNewAgent(event.target.value)}>
              <option value="">选择 Agent 插件…</option>
              {agents.map((plugin) => (
                <option key={plugin.plugin_id} value={plugin.plugin_id}>
                  {plugin.display_name}
                </option>
              ))}
            </select>
            <button className="button button-ghost button-small" onClick={addStage}>
              添加 Agent
            </button>
          </div>
        </SectionCard>

        <SectionCard
          title="阶段配置"
          subtitle={selectedStage ? selectedStage.agent : "选择一个阶段"}
        >
          {selectedStage && selectedStageIndex !== null ? (
            <>
              <div className="stage-detail">
                <div>
                  <span>Agent</span>
                  <strong>{selectedStage.agent}</strong>
                </div>
                <label>
                  <span>LLM 提供商</span>
                  <select
                    value={selectedStage.llm_provider ?? ""}
                    onChange={(event) =>
                      patchStage(selectedStageIndex, {
                        llm_provider: event.target.value || null,
                      })
                    }
                  >
                    <option value="">使用默认 / Mock</option>
                    {llmProviders.map((plugin) => (
                      <option key={plugin.plugin_id} value={plugin.plugin_id}>
                        {plugin.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>知识库</span>
                  <select
                    value={selectedStage.knowledge_base ?? ""}
                    onChange={(event) =>
                      patchStage(selectedStageIndex, {
                        knowledge_base: event.target.value || null,
                      })
                    }
                  >
                    <option value="">不启用</option>
                    {knowledgeBases.map((plugin) => (
                      <option key={plugin.plugin_id} value={plugin.plugin_id}>
                        {plugin.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>工具</span>
                  <select
                    value={selectedStage.tool ?? ""}
                    onChange={(event) =>
                      patchStage(selectedStageIndex, { tool: event.target.value || null })
                    }
                  >
                    <option value="">不启用</option>
                    {tools.map((plugin) => (
                      <option key={plugin.plugin_id} value={plugin.plugin_id}>
                        {plugin.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>人工卡点</span>
                  <input
                    type="checkbox"
                    checked={Boolean(selectedStage.human_gate)}
                    onChange={(event) =>
                      patchStage(selectedStageIndex, { human_gate: event.target.checked })
                    }
                  />
                </label>
                <div>
                  <span>输入源</span>
                  <strong>
                    {definition.sources
                      .map((source) => inputSourceLabel(source.plugin_id))
                      .join("、") || "—"}
                  </strong>
                </div>
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
          输入源节点与 Agent 增删为 Demo 画布扩展【待确认 Q24】;Airflow 连接参数在插件管理中配置。
          画布位置不写入流水线定义(【已确认 Q20】)。
        </div>
      </aside>
    </div>
  );
}
