import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The storefront talks to the Python webhook server. In development it is
// proxied so the browser stays same-origin and no CORS preflight is involved.
const DEV_API_TARGET = process.env.STOREFRONT_DEV_API_TARGET || "http://127.0.0.1:8080";

function vendorChunk(id: string): string | undefined {
  if (!id.includes("node_modules")) return undefined;
  if (/node_modules[\\/](?:react(?:-dom)?|scheduler)[\\/]/.test(id)) return "react-vendor";
  if (/node_modules[\\/](?:@gsap[\\/]react|gsap|lenis|motion(?:-dom|-utils)?)[\\/]/.test(id)) {
    return "animation-vendor";
  }
  if (/node_modules[\\/]lucide-react[\\/]/.test(id)) return "icons-vendor";
  return undefined;
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      "/api/storefront": { target: DEV_API_TARGET, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: vendorChunk,
      },
    },
  },
});
