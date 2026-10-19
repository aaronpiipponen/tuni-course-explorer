/** Vitest runs the TypeScript module tests in a browser-like DOM with its measurement substitute. */
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
    setupFiles: ["./src/testSetup.ts"],
  },
});
