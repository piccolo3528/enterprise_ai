import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router";

import AppLayout from "./components/layout/AppLayout";
import { ProtectedRoute, PublicOnlyRoute } from "./components/layout/RouteGuards";
import Dashboard from "./pages/Dashboard";
import DocumentChunks from "./pages/DocumentChunks";
import KnowledgeBaseDetail from "./pages/KnowledgeBaseDetail";
import KnowledgeBases from "./pages/KnowledgeBases";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import Register from "./pages/Register";
import Search from "./pages/Search";
import Settings from "./pages/Settings";
import SystemStatus from "./pages/SystemStatus";
import BrandLoader from "./components/ui/BrandLoader";

// Loaded on first visit: the Markdown renderer it needs is ~130 kB of the bundle (measured:
// 520 kB with it in the main bundle vs 389 kB before M12), and no other page uses it.
const Chat = lazy(() => import("./pages/Chat"));

function PageLoading() {
  return (
    <BrandLoader label="Loading…" />
  );
}

// The router lives in main.jsx (BrowserRouter), so tests can wrap <App /> in a MemoryRouter.
export default function App() {
  return (
    <Routes>
      <Route element={<PublicOnlyRoute />}>
        <Route path="login" element={<Login />} />
        <Route path="register" element={<Register />} />
      </Route>
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="knowledge-bases" element={<KnowledgeBases />} />
          <Route path="knowledge-bases/:kbId" element={<KnowledgeBaseDetail />} />
          <Route
            path="knowledge-bases/:kbId/documents/:documentId"
            element={<DocumentChunks />}
          />
          <Route
            path="chat"
            element={
              <Suspense fallback={<PageLoading />}>
                <Chat />
              </Suspense>
            }
          />
          <Route path="search" element={<Search />} />
          <Route path="status" element={<SystemStatus />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}
