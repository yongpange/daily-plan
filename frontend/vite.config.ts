import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发模式：/api 代理到 FastAPI（默认 127.0.0.1:8765，可用 DAILY_PLAN_PROXY_TARGET 覆盖）
// 构建产物输出到 ../web，由 FastAPI catch-all 按 SPA 伺服
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.DAILY_PLAN_PROXY_TARGET || 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../web',
    emptyOutDir: true,
  },
})
