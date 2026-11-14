import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Les points d'entrée d'origine (index.js, App.js) contiennent du JSX dans des
// fichiers .js : on demande à l'outil de les traiter comme tels plutôt que de
// les renommer.
export default defineConfig({
  plugins: [react({ include: /\.(js|jsx)$/ })],
  esbuild: { loader: 'jsx', include: /\.(js|jsx)$/, exclude: /node_modules/ },
  optimizeDeps: { esbuildOptions: { loader: { '.js': 'jsx' } } },
  // Chemins relatifs : le même build fonctionne à la racine d'un site statique
  // et sous /dashboard/ quand c'est l'API qui le sert.
  base: './',
  build: { outDir: 'build' },
});
