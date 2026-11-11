import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` serves the UI on 5173 and forwards the API to a CastForge server on 8777 (the test port);
// `npm run build` writes app/ui/, which `python castforge.py app` serves at /.
const api = "http://localhost:8777";
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {outDir: "../app/ui", emptyOutDir: true, chunkSizeWarningLimit: 1200},
  server: {proxy: Object.fromEntries(["/api", "/media", "/library-media", "/static"].map(p => [p, api]))},
});
