import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { registerSW } from "virtual:pwa-register";

import { App } from "./App";
import { BestaetigungProvider } from "./components/ConfirmDialog";
import { mutationToasts, ToastProvider } from "./components/Toast";
import { AuthProvider } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import { pruefeGeraeteWeiche } from "./office/geraeteWeiche";
import { istOfficeHost } from "./office/hostname";
import "./index.css";

const istOffice = istOfficeHost();

// Vor dem ersten Rendern: passt die Oberflaeche nicht zur Fensterbreite, auf
// die andere Subdomain umleiten. Danach nichts mehr aufbauen -- der Browser
// laedt ohnehin gleich neu.
const wirdUmgeleitet = pruefeGeraeteWeiche(istOffice);

// Nur die Handy-App ist eine PWA. Die Desktop-Oberflaeche soll weder
// precachen noch installierbar sein -- am Schreibtisch ist eine Verbindung
// vorausgesetzt, und ein Service Worker wuerde dort nur Update-Verwirrung
// stiften. Service-Worker-Scopes sind ohnehin origin-gebunden, die beiden
// Subdomains kaemen sich also nicht in die Quere.
if (!istOffice && !wirdUmgeleitet) {
  registerSW({ immediate: true });
}

const queryClient = new QueryClient({
  mutationCache: new MutationCache({
    onSuccess: (_data, _vars, _ctx, mutation) => mutationToasts.erfolg(mutation.meta),
    onError: (err, _vars, _ctx, mutation) =>
      mutationToasts.fehler(err, mutation.options.onError !== undefined, mutation.meta),
  }),
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

if (!wirdUmgeleitet) {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ThemeProvider>
            <ToastProvider>
              <BestaetigungProvider>
                <AuthProvider>
                  <App istOffice={istOffice} />
                </AuthProvider>
              </BestaetigungProvider>
            </ToastProvider>
          </ThemeProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </StrictMode>,
  );
}
