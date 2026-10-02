import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const outputDir = path.join(projectRoot, 'resources/statistics_web')

export default defineConfig({
  base: './',
  plugins: [
    react(),
    tailwindcss(),
    {
      name: 'copy-desktop-assets',
      closeBundle() {
        fs.copyFileSync(
          path.join(projectRoot, 'resources/icons/2.10随机工具.ico'),
          path.join(outputDir, 'app-icon.ico'),
        )
        fs.copyFileSync(
          path.join(projectRoot, 'resources/app/source_slot_20_help.png'),
          path.join(outputDir, 'source_slot_20_help.png'),
        )
      },
    },
  ],
  resolve: {
    alias: {
      '@': path.resolve(path.dirname(fileURLToPath(import.meta.url)), './src'),
    },
  },
  build: {
    outDir: outputDir,
    emptyOutDir: true,
  },
})
