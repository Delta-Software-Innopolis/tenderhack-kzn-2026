import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/search-api': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/search-api/, ''),
      },
      '/extract-api': {
        target: 'http://100.106.102.97:8002',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/extract-api/, ''),
      },
    },
  },
})
