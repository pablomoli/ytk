import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { playwright } from "@vitest/browser-playwright";

// Browser tests use a separate config because Vite+'s application config
// cannot currently be loaded by the standalone Vitest runner.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": new URL("./src", import.meta.url).pathname },
  },
  optimizeDeps: {
    include: ["postprocessing", "react-dom/client", "three"],
  },
  test: {
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    browser: {
      enabled: true,
      provider: playwright(),
      headless: true,
      instances: [{ browser: "chromium" }],
    },
  },
});
