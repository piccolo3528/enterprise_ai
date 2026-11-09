import { Navigate, Route, Routes } from "react-router";

import AppLayout from "./components/layout/AppLayout";
import NotFound from "./pages/NotFound";
import SystemStatus from "./pages/SystemStatus";

// The router lives in main.jsx (BrowserRouter), so tests can wrap <App /> in a MemoryRouter.
export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        {/* No dashboard yet, so the home page is the status page for now. */}
        <Route index element={<Navigate to="/status" replace />} />
        <Route path="status" element={<SystemStatus />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
