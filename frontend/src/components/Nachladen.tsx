import { Component, Suspense, lazy, type ComponentType, type ErrorInfo, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { SkeletonList } from "./Skeleton";

const PAUSEN_MS = [400, 1200];

/** `React.lazy` mit zwei stillen Wiederholungen: ein kurzer Netzwechsel (Handy im
 * Tunnel) soll nicht gleich die Fehlerseite zeigen. Scheitert es endgueltig,
 * faengt `SeitenRahmen` den Fehler ab. */
export function lazyMitRetry<T extends ComponentType<any>>(laden: () => Promise<{ default: T }>) {
  return lazy(async () => {
    for (let versuch = 0; ; versuch++) {
      try {
        return await laden();
      } catch (fehler) {
        if (versuch >= PAUSEN_MS.length) throw fehler;
        await new Promise((r) => setTimeout(r, PAUSEN_MS[versuch]));
      }
    }
  });
}

// Nach einem Deploy existieren die alten Chunk-Dateinamen nicht mehr; die offene
// Sitzung kennt sie aber noch. Browser melden das je nach Engine unterschiedlich.
export function istLadefehler(fehler: unknown): boolean {
  const text = fehler instanceof Error ? `${fehler.name} ${fehler.message}` : String(fehler);
  return /ChunkLoadError|Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS/i.test(
    text,
  );
}

interface GrenzeProps {
  children: ReactNode;
  /** Wechselt der Wert (Seitenwechsel), wird ein gemerkter Ladefehler verworfen. */
  ort?: string;
}

/** Zeigt bei einem Ladefehler eines nachgeladenen Seitenteils einen Neuladen-Hinweis.
 * Andere Fehler werden unveraendert weitergereicht (kein stilles Verschlucken). */
export class LadefehlerGrenze extends Component<GrenzeProps, { fehler: unknown }> {
  state = { fehler: null as unknown };

  static getDerivedStateFromError(fehler: unknown) {
    return { fehler };
  }

  componentDidUpdate(vorher: GrenzeProps) {
    if (this.state.fehler !== null && vorher.ort !== this.props.ort) this.setState({ fehler: null });
  }

  componentDidCatch(fehler: unknown, info: ErrorInfo) {
    if (!istLadefehler(fehler)) return;
    console.warn("Seitenteil konnte nicht geladen werden", fehler, info.componentStack);
  }

  render() {
    const { fehler } = this.state;
    if (fehler === null) return this.props.children;
    if (!istLadefehler(fehler)) throw fehler;
    return (
      <div role="alert" className="mx-auto max-w-md p-6 text-center">
        <p className="text-[17px] font-semibold text-label">Diese Seite konnte nicht geladen werden</p>
        <p className="mt-1.5 text-[13px] text-label2">
          Vermutlich gibt es eine neue App-Version oder die Verbindung ist unterbrochen. Neu laden holt die aktuelle Fassung.
        </p>
        <button type="button" onClick={() => window.location.reload()} className="btn-ap-capsule btn-ap-capsule-primary mt-4">
          Seite neu laden
        </button>
      </div>
    );
  }
}

function SeitenFallback() {
  return (
    <div role="status" aria-busy="true" className="p-3">
      <span className="sr-only">Lädt…</span>
      <SkeletonList count={3} />
    </div>
  );
}

/** Rahmen um nachgeladene Seiten (Outlet bzw. Routes): Fallback waehrend des Ladens und
 * Fehlerhinweis. Ein Seitenwechsel verwirft einen gemerkten Ladefehler, ohne die
 * Seite neu aufzubauen. */
export function SeitenRahmen({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return (
    <LadefehlerGrenze ort={pathname}>
      <Suspense fallback={<SeitenFallback />}>{children}</Suspense>
    </LadefehlerGrenze>
  );
}
