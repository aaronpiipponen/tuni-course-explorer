/** Vite build and dev configuration. Runtime API calls are same-origin. */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { wikiPlugin } from "./tools/wiki/plugin.mjs";

export default defineConfig({
  envDir: false,
  plugins: [wikiPlugin(), react(), tailwindcss()],
  base: "/",
  build: { outDir: "dist", assetsDir: "assets", emptyOutDir: true },
  server: { host: "127.0.0.1" },
});
