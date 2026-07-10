import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Vite+ beta's integrated `vp test` is broken (missing vitest bin), and its
// vite.config.ts defineConfig hook crashes upstream vitest. So tests run on
// plain vitest with this isolated config. Invoke with: pnpm exec vitest run
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
