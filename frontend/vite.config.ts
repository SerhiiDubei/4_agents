import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/compile-from-params': 'http://localhost:8000',
      '/compile-from-session': 'http://localhost:8000',
      '/generate-seed': 'http://localhost:8000',
      '/generate-game': 'http://localhost:8000',
      '/init-questions': 'http://localhost:8000',
      '/init-create-character': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
  },
})
