import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Local dev only: mimics what nginx does in the container (route /api/* to each service).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api/auth': 'http://localhost:8001',
      '/api/inventory': 'http://localhost:8002',
      '/api/bookings': 'http://localhost:8003',
      '/api/payments': 'http://localhost:8004',
      '/api/tickets': 'http://localhost:8005',
    },
  },
})
