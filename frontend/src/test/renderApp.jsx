import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import App from "../App";
import { AuthProvider } from "../context/AuthContext";

/** Render the whole app at `path`, with the real AuthProvider (the API modules are mocked). */
export function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

export const TEST_USER = {
  id: "8f6f1c2e-0000-4000-8000-000000000001",
  email: "ana@example.com",
  full_name: "Ana Silva",
  created_at: "2026-11-09T10:00:00Z",
};
