import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Fail loudly instead of silently drifting to 5174 when a stale dev server
    // is still holding the port — a moved port looks exactly like a broken app.
    strictPort: true,
    // Proxy keeps the frontend origin-clean and means no CORS surprises
    // if we ever demo from a different host.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
