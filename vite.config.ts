import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  root: "frontend",
  publicDir: false,
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
  build: {
    outDir: "../public",
    emptyOutDir: false,
    manifest: true,
    sourcemap: true,
    target: "es2020",
    rollupOptions: {
      input: {
        outlier: resolve(__dirname, "frontend/index.html"),
        legacy: resolve(__dirname, "frontend/legacy.html"),
      },
      output: {
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
});
