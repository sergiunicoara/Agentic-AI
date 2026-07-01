import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/ui/',
  server: {
    proxy: {
      '/ws': { target: 'ws://localhost:8080', ws: true },
      '/a2a': { target: 'http://localhost:8080' },
      '/health': { target: 'http://localhost:8080' },
    }
  }
})
