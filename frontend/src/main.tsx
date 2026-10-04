import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { registerSW } from "virtual:pwa-register";

import { App } from "./App";
import { authStore } from "./api/authStore";
import { initFehlerbericht } from "./bugreport";
import { AuthProvider } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import { pruefeGeraeteWeiche } from "./office/geraeteWeiche";
import { istOfficeHost } from "./office/hostname";
import "./index.css";

// Die /me-Query lebt nur im React-Baum (AuthProvider); der Fehlerbericht braucht
// aber schon vor dem ersten Render Zugriff. Die IDs und die Rolle stehen als
// Claims (sub, mandant_id, role) im Access-Token -- reine Dekodierung, kein
// Netzwerkzugriff, und es werden weder Namen noch E-Mails gelesen.
function sitzungAusToken() {
  const token = authStore.getActiveAccessToken();
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))) as {
      sub?: string;
      mandant_id?: string | null;
      role?: string;
    };
    return {
      user_id: payload.sub,
      mandant_id: payload.mandant_id ?? undefined,
      rolle: payload.role,
      flags: authStore.isImpersonating() ? ["impersonation"] : undefined,
    };
  } catch {
    return null;
  }
}

// Vor allem anderen, damit auch frueh auftretende Fehler und Requests erfasst werden.
initFehlerbericht({
  appVersion: __APP_VERSION__,
  commitSha: __GIT_COMMIT__,
  getSitzung: sitzungAusToken,
});

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
            <AuthProvider>
              <App istOffice={istOffice} />
            </AuthProvider>
          </ThemeProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </StrictMode>,
  );
}
