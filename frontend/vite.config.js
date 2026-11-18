import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const path = relative => fileURLToPath(new URL(relative, import.meta.url))

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: path('../web/assets'),
    emptyOutDir: false,
    rollupOptions: {
      input: path('./src/main.js'),
      output: {
        entryFileNames: 'assistant.js',
        inlineDynamicImports: true,
      },
    },
  },
})
