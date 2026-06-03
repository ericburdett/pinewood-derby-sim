import { defineConfig } from "vite";

// base: "./" keeps every asset reference relative so the same build works at the site
// root in dev and under a project subpath on GitHub Pages. The Pyodide runtime + engine
// zip live in public/ (vendored, same-origin — PRD AC-P1, no CDN).
export default defineConfig({
  base: "./",
  build: { target: "es2022" },
  // Pyodide is loaded at runtime from the vendored same-origin /pyodide/ dir, not bundled.
  optimizeDeps: { exclude: ["pyodide"] },
});
