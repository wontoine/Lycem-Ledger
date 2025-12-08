import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import autoprefixer from "autoprefixer";
import tailwindcssPostcss from "@tailwindcss/postcss";

// https://vitejs.dev/config/
export default defineConfig({
  // Enable React support via the official Vite plugin
  plugins: [react()],

  // Configure the local development server
  server: {
    // Run frontend on port 3003 to avoid conflicts with standard ports (like Django's 8000)
    port: 3003,
    host: "0.0.0.0",
    allowedHosts: ["turing.cs.olemiss.edu"],
    // Proxy API requests to the backend to avoid browser CORS and public port exposure
    // Browser calls http://turing.cs.olemiss.edu:3003/api/... and Vite forwards to Django
    proxy: {
      "/api": {
        // Change target if your backend runs elsewhere; can be overridden with VITE_PROXY_TARGET env
        target: process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
      },
      // Also forward auth-only paths used by some components that omit the /api prefix
      "/auth": {
        target: process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
      },
    },
  },

  // CSS and PostCSS Configuration
  css: {
    postcss: {
      plugins: [
        // Integrate Tailwind CSS processing
        tailwindcssPostcss(),
        // Automatically add vendor prefixes for better browser compatibility
        autoprefixer(),
      ],
    },
  },
});