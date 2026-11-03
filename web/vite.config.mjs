/** Vite build and dev configuration for the browser app, whose runtime API calls are same-origin. */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { compressPlugin } from "./tools/compress.mjs";
import { wikiPlugin } from "./tools/wiki/plugin.mjs";

export default defineConfig({
  envDir: false,
  plugins: [wikiPlugin(), react(), tailwindcss(), compressPlugin()],
  base: "/",
  build: { outDir: "dist", assetsDir: "assets", emptyOutDir: true },
  server: { host: "127.0.0.1" },
});
