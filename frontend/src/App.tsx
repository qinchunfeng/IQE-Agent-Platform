import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./Layout";
import { ToastProvider } from "./Toast";
import { CanvasPage } from "./pages/CanvasPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DataSourcesPage } from "./pages/DataSourcesPage";
import { ExperimentsPage } from "./pages/ExperimentsPage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { PluginsPage } from "./pages/PluginsPage";
import { TraceDetailPage } from "./pages/TraceDetailPage";
import { TracesPage } from "./pages/TracesPage";

export default function App() {
  return (
    <ToastProvider>
      <BrowserRouter
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<DashboardPage />} />
            <Route path="canvas" element={<CanvasPage />} />
            <Route path="traces" element={<TracesPage />} />
            <Route path="traces/:traceId" element={<TraceDetailPage />} />
            <Route path="data-sources" element={<DataSourcesPage />} />
            <Route path="plugins" element={<PluginsPage />} />
            <Route path="knowledge" element={<KnowledgePage />} />
            <Route path="experiments" element={<ExperimentsPage />} />
            <Route path="*" element={<div className="empty">页面不存在</div>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  );
}
