import { Camera, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { sammleKontext } from "../index";
import { FehlerberichtDialog, type BerichtStart, type MeldeErgebnis, type RahmenKomponente } from "./FehlerberichtDialog";
import { IGNORIEREN_ATTRIBUT, nimmScreenshot } from "./screenshot";

export interface FehlerberichtSteuerung {
  /** Ob der Nutzer melden darf -- steuert auch, ob Menü-Einträge angezeigt werden. */
  verfuegbar: boolean;
  /** Sofort-Screenshot der aktuellen Ansicht, dann Editor (Tastenkürzel, Office-Menü). */
  aufnehmen: () => void;
  /** Für Seiten, die selbst nicht der fehlerhafte Bildschirm sind (Feld-App "Mehr"). */
  aufnahmemodusStarten: () => void;
}

const Kein: FehlerberichtSteuerung = { verfuegbar: false, aufnehmen: () => undefined, aufnahmemodusStarten: () => undefined };
const Kontext = createContext<FehlerberichtSteuerung>(Kein);

export function useFehlerbericht(): FehlerberichtSteuerung {
  return useContext(Kontext);
}

export function istKuerzel(e: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "shiftKey" | "altKey">): boolean {
  return (e.ctrlKey || e.metaKey) && e.shiftKey && !e.altKey && e.key.toLowerCase() === "b";
}

const naechsterFrame = () => new Promise<void>((r) => requestAnimationFrame(() => r()));

export interface FehlerberichtWidgetProps {
  darfMelden: boolean;
  apiUpload: (formData: FormData) => Promise<MeldeErgebnis>;
  Rahmen: RahmenKomponente;
  /** Wird beim Start des Aufnahmemodus aufgerufen (Router: navigate(-1)). */
  zurueck?: () => void;
  getRoute?: () => string;
  appVersion?: string;
  commitSha?: string;
  /** Dauerhafter Button -- vorbereitet, laut Design-Regel standardmäßig aus. */
  schwebenderButton?: boolean;
  children?: ReactNode;
}

export function FehlerberichtProvider({
  darfMelden,
  apiUpload,
  Rahmen,
  zurueck,
  getRoute = () => window.location.pathname,
  appVersion,
  commitSha,
  schwebenderButton = false,
  children,
}: FehlerberichtWidgetProps) {
  const [modus, setModus] = useState(false);
  const [bericht, setBericht] = useState<BerichtStart | null>(null);
  const laeuft = useRef(false);
  const offen = useRef(false);
  offen.current = bericht !== null;

  const aufnehmen = useCallback(async () => {
    if (!darfMelden || laeuft.current || offen.current) return;
    laeuft.current = true;
    setModus(false);
    try {
      // Snapshot einmalig beim Öffnen: Vorschau und Versand zeigen denselben Stand.
      const kontext = sammleKontext();
      // Zwei Frames, damit Kapsel/Menü sicher aus dem DOM sind, bevor gerendert wird.
      await naechsterFrame();
      await naechsterFrame();
      let original: Blob | null = null;
      let aufnahmeFehlgeschlagen = false;
      try {
        original = await nimmScreenshot();
      } catch {
        aufnahmeFehlgeschlagen = true;
      }
      setBericht({ kontext, original, aufnahmeFehlgeschlagen });
    } finally {
      laeuft.current = false;
    }
  }, [darfMelden]);

  const aufnahmemodusStarten = useCallback(() => {
    if (!darfMelden) return;
    setModus(true);
    zurueck?.();
  }, [darfMelden, zurueck]);

  useEffect(() => {
    if (!darfMelden) return;
    function aufTaste(e: KeyboardEvent) {
      if (!istKuerzel(e)) return;
      e.preventDefault();
      void aufnehmen();
    }
    window.addEventListener("keydown", aufTaste);
    return () => window.removeEventListener("keydown", aufTaste);
  }, [darfMelden, aufnehmen]);

  useEffect(() => {
    if (!modus) return;
    function aufEscape(e: KeyboardEvent) {
      if (e.key === "Escape") setModus(false);
    }
    window.addEventListener("keydown", aufEscape);
    return () => window.removeEventListener("keydown", aufEscape);
  }, [modus]);

  // Verliert der Nutzer das Recht (Logout/Impersonation-Ende), sofort alles schließen.
  useEffect(() => {
    if (!darfMelden) {
      setModus(false);
      setBericht(null);
    }
  }, [darfMelden]);

  const steuerung = useMemo<FehlerberichtSteuerung>(
    () => ({ verfuegbar: darfMelden, aufnehmen: () => void aufnehmen(), aufnahmemodusStarten }),
    [darfMelden, aufnehmen, aufnahmemodusStarten],
  );

  return (
    <Kontext.Provider value={steuerung}>
      {children}
      {darfMelden && modus && (
        <div
          {...{ [IGNORIEREN_ATTRIBUT]: "" }}
          className="fixed left-1/2 z-40 flex max-w-[calc(100vw-24px)] -translate-x-1/2 items-center gap-1 rounded-full bg-tint-solid py-1 pr-1 pl-4 text-white shadow-[0_4px_16px_rgba(0,0,0,.3)]"
          style={{ bottom: "calc(76px + env(safe-area-inset-bottom))" }}
          role="region"
          aria-label="Fehler melden – Aufnahmemodus"
        >
          <button type="button" onClick={() => void aufnehmen()} className="flex min-h-10 items-center gap-2 text-left text-[13px] font-semibold">
            <Camera size={16} strokeWidth={2} className="shrink-0" aria-hidden="true" />
            <span>Zum Fehler wechseln, dann hier tippen · Aufnehmen</span>
          </button>
          <button
            type="button"
            onClick={() => setModus(false)}
            aria-label="Abbrechen"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full"
          >
            <X size={18} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>
      )}
      {darfMelden && schwebenderButton && !modus && !bericht && (
        <button
          {...{ [IGNORIEREN_ATTRIBUT]: "" }}
          type="button"
          onClick={() => void aufnehmen()}
          aria-label="Fehler melden"
          className="btn-ap-capsule btn-ap-capsule-primary fixed right-4 bottom-20 z-40 shadow-[0_4px_16px_rgba(0,0,0,.3)]"
        >
          <Camera size={18} strokeWidth={2} aria-hidden="true" />
          Fehler melden
        </button>
      )}
      {darfMelden && bericht && (
        <FehlerberichtDialog
          start={bericht}
          onClose={() => setBericht(null)}
          Rahmen={Rahmen}
          apiUpload={apiUpload}
          route={getRoute()}
          appVersion={appVersion}
          commitSha={commitSha}
        />
      )}
    </Kontext.Provider>
  );
}
