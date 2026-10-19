/** Vite build configuration for the separately built administration console. */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  envDir: false,
  plugins: [react()],
  base: "/",
  build: { outDir: "dist", assetsDir: "assets", emptyOutDir: true },
  server: { host: "127.0.0.1" },
});
