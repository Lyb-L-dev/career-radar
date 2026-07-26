import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
import { inspectAttr } from 'kimi-plugin-inspect-react'

// https://vite.dev/config/
export default defineConfig({
  // 生产环境由 FastAPI 在站点根路径托管，绝对资源路径可支持任意 SPA 深链接刷新。
  base: '/',
  plugins: [inspectAttr(), react()],
  server: {
    port: 7100,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
