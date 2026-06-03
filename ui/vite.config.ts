import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [svelte()],
  define: {
    'import.meta.env.VITE_WS_PORT': JSON.stringify(process.env.WS_PORT || '9741')
  },
  server: {
    host: '127.0.0.1',
    port: 1420,
    strictPort: true
  },
  clearScreen: false
});
