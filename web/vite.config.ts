import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In production FastAPI serves the built files from web/dist (same origin, no CORS).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5175,
    proxy: { "/api": "http://localhost:8020", "/sample.mp3": "http://localhost:8020" },
  },
});
