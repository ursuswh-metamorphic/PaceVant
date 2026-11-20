import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {alias: {'@': path.resolve(import.meta.dirname, './src/app')}},
  publicDir: 'public',
  server: {proxy: {'/judge': 'http://127.0.0.1:18040', '/mvp': 'http://127.0.0.1:18040', '/healthz': 'http://127.0.0.1:18040'}},
  build: {outDir: 'dist', sourcemap: false},
});
