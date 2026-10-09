import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Older phones (Android Chrome 80+, iOS Safari 13+) must still run the site, so the code is
  // compiled down to syntax they understand.
  build: { target: ["es2019", "chrome80", "safari13", "firefox78", "edge88"] },
  // The backend's FRONTEND_URL / CORS_ORIGINS default to http://localhost:3000
  server: { port: 3000, strictPort: true },
  preview: { port: 3000 },
});
