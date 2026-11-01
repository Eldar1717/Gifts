/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * GIFT MARKET frontend build.
 *
 * The API base URL is injected at build time (VITE_API_URL). When it is a
 * relative path (default `/api`) the dev server proxies to the local backend,
 * which also keeps the live preview working behind the sandbox proxy.
 */
export default defineConfig(() => {
  const apiTarget = process.env.VITE_API_PROXY ?? "http://127.0.0.1:8000";

  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: "0.0.0.0",
      port: 5173,
      strictPort: true,
      allowedHosts: true as const,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
          secure: false,
        },
      },
    },
    preview: {
      host: "0.0.0.0",
      port: 4173,
      allowedHosts: true as const,
    },
    test: {
      environment: "jsdom",
      globals: true,
      include: ["src/**/*.test.{ts,tsx}"],
    },
    build: {
      target: "es2020",
      outDir: "dist",
      sourcemap: false,
    },
  };
});
