import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // Docker Desktop's Windows bind mount doesn't reliably forward
    // filesystem change events (inotify) into the Linux container, so
    // Vite's default watcher silently misses edits — confirmed live: an
    // edited file was correct on disk inside the container, but the dev
    // server kept serving the pre-edit bundle with no HMR update logged
    // at all. Polling works around this at the cost of some CPU overhead.
    watch: {
      usePolling: true,
      interval: 300,
    },
  },
});
