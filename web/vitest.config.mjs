/** Vitest runs TypeScript module tests in a browser-like DOM. */
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { environment: "jsdom", include: ["src/**/*.test.ts"] },
});
