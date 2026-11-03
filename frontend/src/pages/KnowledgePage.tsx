import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Icon } from "../Icon";
import { Badge, EmptyState, SectionCard, Spinner } from "../components/Ui";
import type { KnowledgeEntry } from "../types";
import { CATEGORY_LABELS, formatDateTime, shortId } from "../utils";

export function KnowledgePage() {
  const [items, setItems] = useState<KnowledgeEntry[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (search?: string) => {
    setLoading(true);
    try {
      const result = await api.knowledge(search);
      setItems(result.items);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "加载知识库失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const search = (event: FormEvent) => {
    event.preventDefault();
    load(query.trim() || undefined);
  };

  return (
    <div className="page-stack">
      {error ? <div className="alert alert-danger">{error}</div> : null}

      <section className="knowledge-banner">
        <div className="knowledge-banner-icon">
          <Icon name="knowledge" size={26} />
        </div>
        <div>
          <h2>历史案例,越用越准</h2>
          <p>
            文档场景 3:在 Reviewer 阶段点击“标记入库知识库”,相似案例再次发生时 Triage
            会命中历史案例,置信度从 0.75 提升到 0.92,耗时从 3 分钟降到 30 秒。
          </p>
        </div>
        <Link className="button button-primary" to="/data-sources">
          去推送驱动案例
          <Icon name="arrow" size={15} />
        </Link>
      </section>

      <div className="knowledge-steps">
        <div className="knowledge-step">
          <span>1</span>
          <div>
            <strong>推送案例 A</strong>
            <p>在数据源页面推送 IQE-CASE-017。</p>
          </div>
        </div>
        <div className="knowledge-step">
          <span>2</span>
          <div>
            <strong>标记入库</strong>
            <p>Trace 详情进入 Reviewer 后点击“标记入库知识库”。</p>
          </div>
        </div>
        <div className="knowledge-step">
          <span>3</span>
          <div>
            <strong>推送案例 B</strong>
            <p>再推 IQE-CASE-018,观察知识库命中。</p>
          </div>
        </div>
      </div>

      <SectionCard
        title="知识库条目"
        subtitle={`共 ${items.length} 条;检索使用词频余弦相似度(【已确认 Q7】)`}
        action={
          <form className="search-form" onSubmit={search}>
            <Icon name="search" size={16} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索日志或标题…"
            />
            <button className="button button-ghost button-small" type="submit">
              检索
            </button>
          </form>
        }
      >
        {loading ? (
          <Spinner label="加载知识库…" />
        ) : items.length ? (
          <div className="knowledge-grid">
            {items.map((entry) => (
              <article className="knowledge-card" key={entry.entry_id}>
                <div className="knowledge-card-head">
                  <Badge tone="info">
                    {CATEGORY_LABELS[entry.category] ?? entry.category}
                  </Badge>
                  {entry.score !== undefined && entry.score !== null ? (
                    <Badge tone="success">相似度 {(entry.score * 100).toFixed(0)}%</Badge>
                  ) : null}
                </div>
                <h3>{entry.title}</h3>
                {entry.root_cause ? (
                  <p className="knowledge-root-cause">根因:{entry.root_cause}</p>
                ) : null}
                {entry.summary && entry.summary !== entry.content ? (
                  <p className="knowledge-summary">摘要:{entry.summary}</p>
                ) : null}
                <pre>{entry.content}</pre>
                <div className="knowledge-meta">
                  <span>{formatDateTime(entry.created_at)}</span>
                  {entry.source_trace_id ? (
                    <Link to={`/traces/${entry.source_trace_id}`}>
                      来源 Trace {shortId(entry.source_trace_id, 8)}
                      <Icon name="arrow" size={12} />
                    </Link>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title={query ? "没有匹配的知识" : "知识库为空"}
            description={
              query
                ? "换一个关键词,或清空搜索查看全部条目。"
                : "完成场景 3 的第一步后,知识会自动出现在这里。"
            }
            action={
              <Link className="button button-primary" to="/data-sources">
                推送驱动案例 A
              </Link>
            }
          />
        )}
      </SectionCard>
    </div>
  );
}
