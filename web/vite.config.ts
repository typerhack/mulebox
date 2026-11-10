// Build: static files into the Python package (mulebox/dashboard/app/), which the dashboard's
// aiohttp server serves under /app/, so a build machine needs no Node. Dev: `npm run dev`
// against a stand-in API with made-up data (dev/mock.ts), or, with MULEBOX_DASHBOARD set to a
// dashboard's address, against that dashboard through a proxy.

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import { mockApi } from "./dev/mock.ts";

const dashboard = process.env.MULEBOX_DASHBOARD;
const PROXIED = ["/api", "/healthz", "/login", "/logout", "/static", "/classic"];

export default defineConfig({
  base: "/app/",
  plugins: [react(), tailwindcss(), ...(dashboard ? [] : [mockApi()])],
  build: {
    outDir: "../mulebox/dashboard/app",
    emptyOutDir: true,
    // The page's security policy allows images and fonts from this origin only, never data: URLs.
    assetsInlineLimit: 0,
  },
  server: {
    fs: { allow: [".."] },  // tokens.css is imported from docs/design-system/
    proxy: dashboard ? Object.fromEntries(PROXIED.map((path) => [path, { target: dashboard, changeOrigin: true }])) : undefined,
  },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}", "scripts/*.test.mjs"] },
});
