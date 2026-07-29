import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      // Precaches only the app shell (JS/CSS/HTML/icons) so the PWA can
      // launch offline. Domain data (Vorgaenge/Events for the next 7 Tage,
      // reduced-resolution Fotos) is deliberately NOT handled by generic
      // Workbox runtime caching -- that's the job of the IndexedDB
      // Offline-Outbox (src/offline/), which caches exactly what the spec
      // calls for instead of blanket-caching arbitrary API GETs.
      manifest: {
        name: "SocialCRM",
        short_name: "SocialCRM",
        description: "Auftragsmanagement für den Elektro-Handwerksbetrieb",
        theme_color: "#0f172a",
        background_color: "#0f172a",
        display: "standalone",
        start_url: "/feed",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
      devOptions: {
        enabled: true,
      },
    }),
  ],
  server: {
    port: 5173,
  },
});
