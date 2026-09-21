import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/admin-v2/",
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
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
