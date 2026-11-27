import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import pkg from "./package.json";

const DEMO_API = { target: "http://127.0.0.1:8765", changeOrigin: false };

// The frontend is optional and never on the evaluator path. No runtime network
// dependency: fonts are bundled, there is no analytics and no external API.
export default defineConfig({
  plugins: [react()],
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  // /api is forwarded to the optional local demo API (backend/scripts/demo_api.py), so the page talks to its own
  // origin and the CSP can stay connect-src 'self'. Nothing else is proxied.
  server: { host: "127.0.0.1", port: 5173, strictPort: true, proxy: { "/api": DEMO_API } },
  preview: { host: "127.0.0.1", port: 4173, strictPort: true, proxy: { "/api": DEMO_API } },
  build: { sourcemap: false, target: "es2022" },
  test: { environment: "jsdom", globals: false, include: ["tests/**/*.test.{ts,tsx}"], setupFiles: [] },
});
