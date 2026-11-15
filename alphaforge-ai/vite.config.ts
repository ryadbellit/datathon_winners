import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // L'API Python (flask --app server.src.main run --port 5000) répond sur /api.
  server: { proxy: { '/api': 'http://127.0.0.1:5000' } },
});
