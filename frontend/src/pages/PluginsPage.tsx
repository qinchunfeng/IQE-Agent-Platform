import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { Icon, type IconName } from "../Icon";
import { Badge, Modal, SectionCard, Spinner } from "../components/Ui";
import { useToast } from "../Toast";
import type { PluginCategory, PluginInfo, PluginSchemaField } from "../types";
import { PLUGIN_STATE_LABELS } from "../utils";

const TYPE_ICONS: Record<string, IconName> = {
  input_source: "data",
  agent: "cpu",
  knowledge_base: "knowledge",
  tool: "settings",
  orchestrator: "layers",
  llm_provider: "spark",
  event_bus: "traces",
  storage: "data",
};

function healthTone(plugin: PluginInfo): "success" | "danger" | "neutral" {
  if (!plugin.enabled) return "neutral";
  return plugin.health?.healthy ? "success" : "danger";
}

function healthLabel(plugin: PluginInfo): string {
  if (!plugin.enabled) return "已禁用";
  return plugin.health?.healthy ? "健康" : "不可用";
}

export function PluginsPage() {
  const [categories, setCategories] = useState<PluginCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<PluginInfo | null>(null);
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const { showToast } = useToast();

  const load = useCallback(async () => {
    try {
      const result = await api.plugins(true);
      setCategories(result.categories);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "加载插件失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggle = async (plugin: PluginInfo) => {
    setBusy(plugin.plugin_id);
    try {
      if (plugin.enabled) {
        await api.disablePlugin(plugin.plugin_id);
        showToast(`${plugin.display_name} 已禁用`, "success");
      } else {
        const result = await api.enablePlugin(plugin.plugin_id);
        if (result.health?.healthy) {
          showToast(`${plugin.display_name} 已启用`, "success");
        } else {
          showToast(
            `${plugin.display_name} 已启用,但健康检查未通过:${result.health?.message ?? "未知"}`,
            "error",
          );
        }
      }
      await load();
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : "操作失败", "error");
    } finally {
      setBusy(null);
    }
  };

  const openConfig = (plugin: PluginInfo) => {
    setEditing(plugin);
    setDraft({ ...plugin.config });
  };

  const saveConfig = async () => {
    if (!editing) return;
    setBusy(editing.plugin_id);
    try {
      await api.configurePlugin(editing.plugin_id, draft);
      showToast(`${editing.display_name} 配置已保存`, "success");
      setEditing(null);
      await load();
    } catch (cause) {
      showToast(cause instanceof Error ? cause.message : "保存失败", "error");
    } finally {
      setBusy(null);
    }
  };

  const updateField = (key: string, value: unknown) => {
    setDraft((previous) => ({ ...previous, [key]: value }));
  };

  if (loading) return <Spinner label="加载插件与健康状态…" />;

  return (
    <div className="page-stack">
      {error ? <div className="alert alert-danger">{error}</div> : null}

      <div className="alert alert-info inline-alert">
        <Icon name="alert" size={16} />
        <span>
          文档 7.4:Airflow / Qoder CN 不可用时自动降级。Airflow 默认禁用;Qoder CN
          未配置凭据时,流水线会使用 Mock LLM,并在 Trace 中记录降级原因。
        </span>
      </div>

      {categories.map((category) => (
        <SectionCard
          key={category.type}
          title={
            <span className="category-title">
              <span className="category-icon">
                <Icon name={TYPE_ICONS[category.type] ?? "plugins"} size={18} />
              </span>
              {category.label}
            </span>
          }
          subtitle={`${category.plugins.length} 个插件`}
        >
          <div className="plugin-grid">
            {category.plugins.map((plugin) => (
              <article
                key={plugin.plugin_id}
                className={`plugin-card${plugin.enabled ? "" : " plugin-disabled"}`}
              >
                <div className="plugin-card-head">
                  <div>
                    <h3>{plugin.display_name}</h3>
                    <code>{plugin.plugin_id}</code>
                  </div>
                  <span className={`health-dot health-${healthTone(plugin)}`} title={healthLabel(plugin)} />
                </div>
                <p className="plugin-desc">{plugin.description}</p>
                <div className="plugin-badges">
                  <Badge tone={healthTone(plugin)}>{healthLabel(plugin)}</Badge>
                  <Badge tone="neutral">
                    {PLUGIN_STATE_LABELS[plugin.state] ?? plugin.state}
                  </Badge>
                </div>
                {plugin.health?.message ? (
                  <div className="plugin-health-msg">{plugin.health.message}</div>
                ) : null}
                {Object.keys(plugin.dependencies).length ? (
                  <div className="plugin-deps">
                    {Object.entries(plugin.dependencies).map(([type, ids]) => (
                      <span key={type}>
                        {type}: {(ids ?? []).join(" / ") || "—"}
                      </span>
                    ))}
                  </div>
                ) : null}
                {Object.keys(plugin.capabilities).length ? (
                  <div className="plugin-deps">
                    {Object.entries(plugin.capabilities)
                      .filter(([key]) => key !== "description")
                      .map(([key, value]) => (
                        <span key={key}>
                          {key}: {String(value)}
                        </span>
                      ))}
                  </div>
                ) : null}
                <div className="plugin-actions">
                  <button
                    className={`switch${plugin.enabled ? " on" : ""}`}
                    onClick={() => toggle(plugin)}
                    disabled={busy !== null}
                    aria-pressed={plugin.enabled}
                  >
                    <span className="switch-knob" />
                    {plugin.enabled ? "已启用" : "已禁用"}
                  </button>
                  <button
                    className="button button-ghost button-small"
                    onClick={() => openConfig(plugin)}
                    disabled={busy !== null}
                  >
                    <Icon name="settings" size={14} />
                    配置
                  </button>
                </div>
              </article>
            ))}
          </div>
        </SectionCard>
      ))}

      <Modal
        open={editing !== null}
        title={editing ? `配置 ${editing.display_name}` : ""}
        onClose={() => setEditing(null)}
        footer={
          <>
            <button className="button button-ghost" onClick={() => setEditing(null)}>
              取消
            </button>
            <button
              className="button button-primary"
              onClick={saveConfig}
              disabled={busy !== null}
            >
              {busy ? "保存中…" : "保存配置"}
            </button>
          </>
        }
      >
        {editing ? (
          <PluginConfigForm
            schema={editing.config_schema}
            draft={draft}
            onChange={updateField}
          />
        ) : null}
      </Modal>
    </div>
  );
}

function PluginConfigForm({
  schema,
  draft,
  onChange,
}: {
  schema: Record<string, PluginSchemaField>;
  draft: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
}) {
  const fields = Object.entries(schema);
  if (!fields.length) {
    return <p className="muted">该插件没有可配置项。</p>;
  }
  return (
    <div className="config-form">
      {fields.map(([key, field]) => {
        const value = draft[key];
        const label = field.label ?? key;
        return (
          <label className="config-field" key={key}>
            <div className="config-label">
              <span>
                {label}
                {field.required ? <em>*</em> : null}
              </span>
              <code>{key}</code>
            </div>
            {field.description ? <p>{field.description}</p> : null}
            {field.type === "boolean" ? (
              <span className="checkbox-row">
                <input
                  type="checkbox"
                  checked={Boolean(value)}
                  onChange={(event) => onChange(key, event.target.checked)}
                />
                启用
              </span>
            ) : field.multiline ? (
              <textarea
                value={typeof value === "string" ? value : ""}
                onChange={(event) => onChange(key, event.target.value)}
                rows={10}
                maxLength={field.max_length}
              />
            ) : field.enum ? (
              <select
                value={String(value ?? "")}
                onChange={(event) => onChange(key, event.target.value)}
              >
                {field.enum.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type={field.secret ? "password" : field.type === "string" ? "text" : "number"}
                value={
                  typeof value === "number" || typeof value === "string"
                    ? value
                    : value === null || value === undefined
                      ? ""
                      : String(value)
                }
                step={field.type === "integer" ? 1 : "any"}
                min={field.min}
                max={field.max}
                onChange={(event) => {
                  if (field.type === "integer" || field.type === "number") {
                    const next = event.target.value === "" ? "" : Number(event.target.value);
                    onChange(key, next);
                  } else {
                    onChange(key, event.target.value);
                  }
                }}
              />
            )}
            {field.secret ? (
              <span className="field-hint">
                {value === "***"
                  ? "已配置密钥;保留 *** 表示不修改,输入空字符串表示清除。"
                  : "密钥仅保存于后端,响应与日志中已脱敏。"}
              </span>
            ) : null}
          </label>
        );
      })}
    </div>
  );
}
