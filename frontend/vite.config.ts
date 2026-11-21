import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {alias: {'@': path.resolve(import.meta.dirname, './src/app')}},
  publicDir: 'public',
  // Preserve the browser-facing Host so the backend's same-origin check sees
  // the same authority as the Origin header. Vite's string shorthand rewrites it.
  server: {proxy: Object.fromEntries(['/judge', '/mvp', '/healthz'].map(prefix => [prefix, {
    target:process.env.PACEVANT_API_TARGET || 'http://127.0.0.1:18040', changeOrigin:false,
  }]))},
  build: {outDir: 'dist', sourcemap: false},
});
