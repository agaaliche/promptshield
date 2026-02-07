import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
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
