import type { ReactNode } from "react";

import { Logo } from "../components/brand/Logo";

/** Gemeinsamer Rahmen der Partnerportal-Seiten ohne Anmeldung (Login,
 * Passwort vergessen/zuruecksetzen, Einladung). */
export function PartnerAuthShell({ titel, untertitel, children }: { titel: string; untertitel?: string; children: ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gbg p-4 text-label">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2">
          <Logo variante="wortmarke" hoehe={30} />
          <p className="text-[13px] font-semibold tracking-wide text-label2 uppercase">Partnerportal</p>
        </div>
        <div className="card-ap p-6">
          <h1 className="ap-heading mb-1 text-[22px] font-bold text-label">{titel}</h1>
          {untertitel && <p className="mb-5 text-[15px] text-label2">{untertitel}</p>}
          {!untertitel && <div className="mb-5" />}
          {children}
        </div>
      </div>
    </main>
  );
}

export function FehlerHinweis({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="mb-4 rounded-[var(--radius-ap-input)] bg-st-fehlt-bg px-3 py-2 text-sm text-st-fehlt">
      {children}
    </div>
  );
}

export function ErfolgsHinweis({ children }: { children: ReactNode }) {
  return (
    <p role="status" className="mb-4 rounded-[var(--radius-ap-input)] bg-st-erledigt-bg px-3 py-2 text-sm text-st-erledigt">
      {children}
    </p>
  );
}
