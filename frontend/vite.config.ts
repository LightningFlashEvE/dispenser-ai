import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { readFileSync } from 'fs'
import type { ServerOptions } from 'https'

const useHttps = process.env.USE_HTTPS === 'true'

function httpsOptions(): ServerOptions | undefined {
  if (!useHttps) return undefined

  const certPath = process.env.SSL_CERT_PATH
  const keyPath = process.env.SSL_KEY_PATH
  if (!certPath || !keyPath) {
    throw new Error('USE_HTTPS=true requires SSL_CERT_PATH and SSL_KEY_PATH')
  }

  return {
    cert: readFileSync(certPath),
    key: readFileSync(keyPath),
  }
}

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
    https: httpsOptions(),
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
