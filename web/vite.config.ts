// Build: static files into the Python package (mulebox/dashboard/app/), which the dashboard's
// aiohttp server serves under /app/, so a node needs no Node. Dev: `npm run dev`
// against a stand-in API with made-up data (dev/mock.ts), or, with MULEBOX_DASHBOARD set to a
// dashboard's address, against that dashboard through a proxy.

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import { mockApi } from "./dev/mock.ts";

const dashboard = process.env.MULEBOX_DASHBOARD;
const PROXIED = ["/api", "/healthz", "/login", "/logout"];

// The sign-in page loads before a session exists, so the server lets its stylesheet and the
// fonts through by fixed names (mulebox/dashboard/login.py, PUBLIC_PATHS): `login.css` and
// `fonts/<name>.woff2`. Everything else keeps a hash in its name.
function assetName(info: { names?: string[] }): string {
  const name = info.names?.[0] ?? "";
  if (name === "login.css") return "login.css";
  if (name.endsWith(".woff2")) return "fonts/[name][extname]";
  return "assets/[name]-[hash][extname]";
}

export default defineConfig({
  base: "/app/",
  plugins: [react(), tailwindcss(), ...(dashboard ? [] : [mockApi()])],
  build: {
    outDir: "../mulebox/dashboard/app",
    emptyOutDir: true,
    // The page's security policy allows images and fonts from this origin only, never data: URLs.
    assetsInlineLimit: 0,
    rollupOptions: {
      input: { index: "index.html", login: "login.html" },
      output: { assetFileNames: assetName },
    },
  },
  server: {
    fs: { allow: [".."] },  // tokens.css is imported from docs/design-system/
    proxy: dashboard ? Object.fromEntries(PROXIED.map((path) => [path, { target: dashboard, changeOrigin: true }])) : undefined,
  },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}", "scripts/*.test.mjs"] },
});
