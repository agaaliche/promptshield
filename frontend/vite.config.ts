import { defineConfig, mergeConfig } from 'vite'
import { defineConfig as defineTestConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const API_PORT = process.env.VITE_API_PORT || '8910'
const API_TARGET = `http://127.0.0.1:${API_PORT}`

const viteConfig = defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
      '/health': {
        target: API_TARGET,
        changeOrigin: true,
      },
      '/bitmaps': {
        target: API_TARGET,
        changeOrigin: true,
      },
      '/downloads': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
})

export default mergeConfig(
  viteConfig,
  defineTestConfig({
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
    },
  })
)
