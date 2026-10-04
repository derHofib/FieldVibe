/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_MAPBOX_TOKEN: string | undefined;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Per `define` in vite.config.ts ersetzt (package.json-Version bzw. GIT_COMMIT beim Build).
declare const __APP_VERSION__: string;
declare const __GIT_COMMIT__: string;
