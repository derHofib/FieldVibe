import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";
import { configDefaults } from "vitest/config";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.ico", "favicon-16.png", "favicon-32.png", "apple-touch-icon.png"],
      // Precaches only the app shell (JS/CSS/HTML/icons) so the PWA can
      // launch offline. Domain data (Vorgaenge/Events for the next 7 Tage,
      // reduced-resolution Fotos) is deliberately NOT handled by generic
      // Workbox runtime caching -- that's the job of the IndexedDB
      // Offline-Outbox (src/offline/), which caches exactly what the spec
      // calls for instead of blanket-caching arbitrary API GETs.
      manifest: {
        name: "FieldVibe",
        short_name: "FieldVibe",
        description: "Auftragsmanagement für den Elektro-Handwerksbetrieb",
        theme_color: "#0E1520",
        background_color: "#0E1520",
        display: "standalone",
        start_url: "/feed",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
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
  test: {
    // e2e/ enthaelt Playwright-Specs (playwright.config.ts), die vitest
    // sonst wegen des gleichen "*.spec.ts"-Musters faelschlich einsammelt.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
