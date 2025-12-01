// vite.config.js

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import autoprefixer from "autoprefixer";
// 💡 CHANGE: Import the new PostCSS plugin package
import tailwindcssPostcss from "@tailwindcss/postcss";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],

  css: {
    postcss: {
      plugins: [
        // 💡 CHANGE: Use the new plugin import
        tailwindcssPostcss(),
        autoprefixer(),
      ],
    },
  },
});
