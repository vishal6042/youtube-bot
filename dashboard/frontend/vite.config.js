import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build straight into dashboard/static so the FastAPI server serves the
// bundle — production use stays "python -m dashboard.server", no Node needed.
export default defineConfig({
  plugins: [react()],
  base: "/static/",
  build: {
    outDir: "../static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8787" },
  },
});
