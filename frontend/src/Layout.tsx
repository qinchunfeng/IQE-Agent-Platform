import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "./api";
import { Icon } from "./Icon";

const NAV_ITEMS = [
  { path: "/", label: "仪表盘", icon: "dashboard" as const, end: true },
  { path: "/canvas", label: "流水线画布", icon: "canvas" as const },
  { path: "/traces", label: "Trace 追踪", icon: "traces" as const },
  { path: "/data-sources", label: "数据源", icon: "data" as const },
  { path: "/plugins", label: "插件管理", icon: "plugins" as const },
  { path: "/knowledge", label: "知识库", icon: "knowledge" as const },
  { path: "/experiments", label: "实验面板", icon: "experiment" as const },
];

const PAGE_TITLES: Record<string, { title: string; subtitle: string }> = {
  "/": { title: "运营仪表盘", subtitle: "端到端自动化与 TAT 概览" },
  "/canvas": { title: "流水线画布", subtitle: "6 个 IQE Agent 的可视化编排" },
  "/traces": { title: "Trace 追踪", subtitle: "查看每一次失败处理的完整链路" },
  "/data-sources": { title: "数据源", subtitle: "Mock Jenkins 事件推送与演示案例" },
  "/plugins": { title: "插件管理", subtitle: "8 类插件、健康检查与 Mock 降级" },
  "/knowledge": { title: "知识库", subtitle: "历史案例检索与人工入库" },
  "/experiments": { title: "实验面板", subtitle: "本地 vs 云端成本、TAT 与置信度" },
};

type ApiState = "checking" | "ok" | "down";

export function Layout() {
  const location = useLocation();
  const [apiState, setApiState] = useState<ApiState>("checking");
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        await api.health();
        if (!cancelled) setApiState("ok");
      } catch {
        if (!cancelled) setApiState("down");
      }
    };
    check();
    const timer = window.setInterval(check, 15_000);
    const clock = window.setInterval(() => setNow(new Date()), 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.clearInterval(clock);
    };
  }, []);

  const key = location.pathname.startsWith("/traces/") ? "/traces" : location.pathname;
  const page = PAGE_TITLES[key] ?? { title: "IQE-Agent Platform", subtitle: "" };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Icon name="layers" size={22} />
          </div>
          <div>
            <div className="brand-name">IQE-Agent</div>
            <div className="brand-sub">PLUGIN ORCHESTRATION</div>
          </div>
        </div>

        <nav className="nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.end}
              className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
            >
              <Icon name={item.icon} size={18} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-note">
            <div className="sidebar-note-title">万物插件</div>
            <p>平台内核只做编排,Airflow / Qoder CN 均为可选插件。</p>
          </div>
          <div className="sidebar-version">v0.1.0-demo · 文档 v2.4</div>
        </div>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <div className="topbar-inner">
            <div>
              <h1>{page.title}</h1>
              <p>{page.subtitle}</p>
            </div>
            <div className="topbar-right">
              <span className={`api-pill api-${apiState}`}>
                <span className="api-dot" />
                {apiState === "ok" ? "API 已连接" : apiState === "down" ? "API 未连接" : "连接中"}
              </span>
              <span className="topbar-date">
                {now.toLocaleDateString("zh-CN", {
                  year: "numeric",
                  month: "2-digit",
                  day: "2-digit",
                })}
              </span>
            </div>
          </div>
        </header>
        <main className="page">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
