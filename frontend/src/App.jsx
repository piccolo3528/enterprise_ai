import { Navigate, Route, Routes } from "react-router";

import AppLayout from "./components/layout/AppLayout";
import { ProtectedRoute, PublicOnlyRoute } from "./components/layout/RouteGuards";
import Dashboard from "./pages/Dashboard";
import KnowledgeBaseDetail from "./pages/KnowledgeBaseDetail";
import KnowledgeBases from "./pages/KnowledgeBases";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import Register from "./pages/Register";
import SystemStatus from "./pages/SystemStatus";

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
          <Route path="status" element={<SystemStatus />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}
