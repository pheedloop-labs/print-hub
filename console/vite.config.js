import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vite'

// The console is served two different ways and both have to work.
//
//   dev   `npm run dev` on :5173, proxying /api to the hub on :8080. Nothing
//         is rebuilt by hand; edits appear immediately.
//   prod  `npm run build` emits into printhub/static/, which Flask serves.
//         A hub never needs Node - it only ever serves the built files.
//
// emptyOutDir is on so a renamed or deleted component cannot leave a stale
// asset behind in the output.
export default defineConfig({
  plugins: [svelte()],
  build: {
    outDir: '../printhub/static',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8080', changeOrigin: true },
    },
  },
})
