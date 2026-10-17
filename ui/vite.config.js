import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The build goes inside the Python package, so a tester needs only Python (Phase 7b).
// `npm run dev` proxies /api to `python -m normalization serve` on port 8000.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "../src/normalization/app/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
