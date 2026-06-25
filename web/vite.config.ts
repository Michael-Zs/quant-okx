import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite dev server 代理 /api 与 /ws 到本地 FastAPI（默认 127.0.0.1:8787）
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8787', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8787', ws: true, changeOrigin: true },
    },
  },
})
