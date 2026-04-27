import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const useHttps = process.env.USE_HTTPS === 'true'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    https: useHttps
      ? {
          // 自签名证书（仅供开发/内网测试）
          // 浏览器首次访问会提示"证书不受信任"，点击"高级"→"继续前往"即可
          cert: process.env.SSL_CERT_PATH || undefined,
          key: process.env.SSL_KEY_PATH || undefined,
        }
      : undefined,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
