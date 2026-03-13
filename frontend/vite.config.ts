import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  define: {
    // amazon-cognito-identity-js expects Node.js `global` to exist
    global: "globalThis",
  },
  server: {
    // Proxy is only needed when running the agent locally (uv run python agent/agent.py).
    // When VITE_AGENT_URL points to the deployed AgentCore runtime, remove or comment these out.
    // proxy: {
    //   "/invocations": { target: "http://localhost:8080", changeOrigin: true },
    //   "/ping":         { target: "http://localhost:8080", changeOrigin: true },
    // },
  },
});
