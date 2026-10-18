import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/admin-v2/",
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: "react-vendor",
              test: /node_modules[\\/](?:react(?:-dom)?|scheduler)[\\/]/,
              priority: 30,
            },
            {
              name: "animation-vendor",
              test: /node_modules[\\/](?:@gsap[\\/]react|gsap|lenis|motion(?:-dom|-utils)?)[\\/]/,
              priority: 20,
            },
            {
              name: "icons-vendor",
              test: /node_modules[\\/]lucide-react[\\/]/,
              priority: 10,
            },
            {
              name: "vendor",
              test: /node_modules/,
              maxSize: 200_000,
            },
          ],
        },
      },
    },
  },
  server: {
    proxy: {
      "/admin/notification-sw.js": "http://localhost:8080",
      "/admin/api": "http://localhost:8080",
      "^/admin(?:$|/(?!api(?:/|$)))": {
        target: "http://localhost:8080",
        bypass(req) {
          if (req.method !== "POST") return "/admin-v2/index.html";
        },
      },
    },
  },
});
