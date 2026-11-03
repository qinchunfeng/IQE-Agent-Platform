import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 文档 0.4:前端开发服务器端口 3200(3000/5173/5174 已被本机占用)
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 3200,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 3200,
    strictPort: true,
  },
});
