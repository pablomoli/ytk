import { defineConfig } from "vite-plus";
import react from "@vitejs/plugin-react";

// The SPA is served by FastAPI under /app, so built asset URLs must be
// /app/-prefixed to match the backend's /app/assets mount. The dev server
// proxies backend routes to the hub on :6969.
export default defineConfig({
  base: "/app/",
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:6969",
      "/vault-media": "http://127.0.0.1:6969",
      "/favicon.svg": "http://127.0.0.1:6969",
    },
  },
  fmt: {},
  lint: {
    plugins: ["react", "typescript", "oxc"],
    rules: {
      "react/rules-of-hooks": "error",
      "react/only-export-components": ["warn", { allowConstantExport: true }],
    },
    options: {
      typeAware: true,
      typeCheck: true,
    },
  },
  plugins: [react()],
});
