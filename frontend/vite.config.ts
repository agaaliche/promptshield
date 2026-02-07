import { defineConfig, mergeConfig } from 'vite'
import { defineConfig as defineTestConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const viteConfig = defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8910',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:8910',
        changeOrigin: true,
      },
      '/bitmaps': {
        target: 'http://127.0.0.1:8910',
        changeOrigin: true,
      },
      '/downloads': {
        target: 'http://127.0.0.1:8910',
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
