import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true, // fail loudly instead of silently moving to 5174
    proxy: {
      // The browser only ever talks to localhost:5173. Vite forwards /api/* to FastAPI, so the
      // frontend and backend share one origin: no CORS setup, and (from M5) the SameSite=Strict
      // auth cookie just works. API keys stay on the backend; the frontend has no secrets.
      // 127.0.0.1, not "localhost": Node resolves localhost to IPv6 (::1) first, but uvicorn
      // listens on IPv4 127.0.0.1 by default.
      "/api": { target: "http://127.0.0.1:8000" },
    },
  },
  test: {
    environment: "jsdom", // a simulated browser DOM inside Node
    setupFiles: "./src/test/setup.js",
  },
});
