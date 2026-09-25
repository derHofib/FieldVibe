import { Clock } from "lucide-react";
import { Outlet, useLocation } from "react-router-dom";

import { useAppLiveDaten } from "../hooks/useAppLiveDaten";
import { BottomNav } from "./BottomNav";
import { ImpersonationBanner } from "./ImpersonationBanner";

// Deckt sich mit den vier Tabs in BottomNav.tsx -- hier nur fuer den
// unsichtbaren Seiten-h1 gebraucht (siehe unten), deshalb nicht von dort
// importiert, um BottomNav nicht wegen einer reinen a11y-Kleinigkeit
// veroeffentlichen zu muessen.
const TAB_TITEL: { praefix: string; titel: string }[] = [
  { praefix: "/projekte", titel: "Projekte" },
  { praefix: "/mehr", titel: "Mehr" },
  { praefix: "/feed", titel: "Aufträge" },
];

function useSeitentitel(): string {
  const { pathname } = useLocation();
  return TAB_TITEL.find((t) => pathname.startsWith(t.praefix))?.titel ?? "FieldVibe";
}

/** Feld-App-Rahmen (Abschnitt 5.3): kein persistenter Marken-Header mehr --
 * jede Seite traegt ihre eigene Ueberschrift (AbschnittskopfA), und Suche/
 * Darstellung/Einstellungen/Abmelden leben vollstaendig im "Mehr"-Tab
 * (siehe MehrPage.tsx), der alles abdeckt, was der alte, rollen-gated
 * Header-Link vorher nur teilweise zeigte. Uebrig bleibt hier nur, was
 * unabhaengig von der aktuellen Seite gilt: Impersonation-Banner,
 * Offline-Hinweis, ein schmaler Sync-Ausstehend-Streifen (ersetzt den
 * frueheren outboxCount-Badge im Header) und die Tab-Bar. */
export function FeldLayout() {
  const { outboxCount, isOnline } = useAppLiveDaten();
  const seitentitel = useSeitentitel();

  return (
    <div className="min-h-screen bg-gbg text-label" style={{ paddingBottom: "calc(61px + env(safe-area-inset-bottom))" }}>
      <ImpersonationBanner />
      {!isOnline && (
        <div className="bg-st-arbeit-bg px-4 py-1.5 text-center text-[13px] font-medium text-st-arbeit">
          Offline – Änderungen werden gespeichert und später synchronisiert
        </div>
      )}
      {isOnline && outboxCount > 0 && (
        <div className="flex items-center justify-center gap-1.5 bg-st-arbeit-bg px-4 py-1.5 text-center text-[13px] font-medium text-st-arbeit">
          <Clock size={13} strokeWidth={2} aria-hidden="true" />
          {outboxCount} noch nicht synchronisiert
        </div>
      )}
      <main className="mx-auto max-w-2xl px-3 py-4">
        {/* Visuell kein Marken-Header mehr (s.o.), aber axe-core verlangt zu
         * Recht genau eine h1 pro Seite -- muss innerhalb eines Landmarks
         * (hier <main>) liegen, sonst meldet axe "region". AbschnittskopfA
         * (h2) darunter bleibt die eigentliche, sichtbare Seitenueberschrift. */}
        <h1 className="sr-only">{seitentitel}</h1>
        <Outlet />
      </main>
      <BottomNav />
    </div>
  );
}
