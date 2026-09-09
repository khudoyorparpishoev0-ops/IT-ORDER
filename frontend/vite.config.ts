import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';
import { readFileSync, writeFileSync } from 'node:fs';
import type { Plugin } from 'vite';

/**
 * Дата сборки попадает в бандл. По ней в панели видно, свежая ли версия:
 * иначе после обновления сервера остаётся гадать, показывает браузер новый
 * код или старый из кэша.
 */
const BUILD_DATE = new Date().toISOString().slice(0, 10);
const BUILD_VERSION = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14);

/**
 * Файлы из public/ Vite копирует как есть, поэтому версию в service worker
 * подставляем после сборки. Без неё воркер не узнал бы об обновлении
 * панели и продолжал бы отдавать ассеты прошлой версии из своего кэша.
 */
function stampServiceWorker(): Plugin {
  return {
    name: 'hona-stamp-sw',
    apply: 'build',
    closeBundle() {
      const file = fileURLToPath(new URL('./dist/sw.js', import.meta.url));
      const src = readFileSync(file, 'utf8');
      writeFileSync(file, src.replace('__BUILD_VERSION__', BUILD_VERSION));
    },
  };
}

export default defineConfig({
  define: { __BUILD_DATE__: JSON.stringify(BUILD_DATE) },
  plugins: [react(), stampServiceWorker()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  // Один и тот же прокси нужен и dev-серверу, и preview: панель ходит
  // в API относительными путями, как в проде через nginx.
  server: {
    port: 5173,
    // API отдаётся тем же origin через nginx в проде; в dev проксируем на backend.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
});
