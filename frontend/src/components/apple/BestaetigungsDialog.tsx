import { useEffect, useRef, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

/** Bestaetigungsdialog (Ersatz fuer window.confirm): iOS-artiger Alert, zentriert,
 * `role="alertdialog"`. Fokus startet auf "Abbrechen" (sichere Wahl bei destruktiven
 * Aktionen), Tab wird im Dialog gehalten, Escape und Klick auf den Hintergrund
 * brechen ab, danach kehrt der Fokus zum ausloesenden Element zurueck. */
export function BestaetigungsDialog({
  titel,
  text,
  bestaetigenLabel,
  abbrechenLabel = "Abbrechen",
  destruktiv = false,
  onBestaetigen,
  onAbbrechen,
}: {
  titel: string;
  text: string;
  bestaetigenLabel: string;
  abbrechenLabel?: string;
  destruktiv?: boolean;
  onBestaetigen: () => void;
  onAbbrechen: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const abbrechenRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const vorher = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    abbrechenRef.current?.focus();
    return () => vorher?.focus();
  }, []);

  function aufTaste(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      e.stopPropagation();
      onAbbrechen();
      return;
    }
    if (e.key !== "Tab") return;
    const knoepfe = dialogRef.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)");
    if (!knoepfe || knoepfe.length === 0) return;
    const erster = knoepfe[0];
    const letzter = knoepfe[knoepfe.length - 1];
    if (e.shiftKey && document.activeElement === erster) {
      e.preventDefault();
      letzter.focus();
    } else if (!e.shiftKey && document.activeElement === letzter) {
      e.preventDefault();
      erster.focus();
    }
  }

  return createPortal(
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 px-6"
      onClick={onAbbrechen}
      onKeyDown={aufTaste}
    >
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="bestaetigung-titel"
        aria-describedby="bestaetigung-text"
        onClick={(e) => e.stopPropagation()}
        className="ap-sheet-surface w-full max-w-[320px] rounded-[14px] bg-gbg p-5 text-center shadow-xl"
      >
        <h2 id="bestaetigung-titel" className="text-[17px] font-semibold text-label">
          {titel}
        </h2>
        <p id="bestaetigung-text" className="mt-1.5 whitespace-pre-line text-[13px] text-label2">
          {text}
        </p>
        <div className="mt-5 flex flex-col gap-2">
          <button
            type="button"
            onClick={onBestaetigen}
            className={`btn-ap-capsule w-full ${destruktiv ? "" : "btn-ap-capsule-primary"}`}
            style={destruktiv ? { background: "var(--st-fehlt-bg)", color: "var(--st-fehlt-text)" } : undefined}
          >
            {bestaetigenLabel}
          </button>
          <button ref={abbrechenRef} type="button" onClick={onAbbrechen} className="btn-ap-capsule btn-ap-capsule-secondary w-full">
            {abbrechenLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export interface BestaetigungsOptionen {
  titel?: string;
  bestaetigenLabel?: string;
  abbrechenLabel?: string;
  /** Standard: aus dem Text abgeleitet (loeschen, stornieren, ...). */
  destruktiv?: boolean;
}

interface Anfrage extends BestaetigungsOptionen {
  id: number;
  text: string;
  loesen: (ergebnis: boolean) => void;
}

// Modulweiter Speicher statt Hook: die Aufrufer sind ueberwiegend Klick-Handler
// in tief verschachtelten Seiten, die nur ein `await bestaetigen(...)` brauchen.
let laufendeNummer = 0;
let aktuell: Anfrage | null = null;
const wartend: Anfrage[] = [];
const abonnenten = new Set<() => void>();

function melden() {
  abonnenten.forEach((fn) => fn());
}

function abonnieren(fn: () => void) {
  abonnenten.add(fn);
  return () => {
    abonnenten.delete(fn);
  };
}

const VERBEN: [RegExp, string][] = [
  [/endgültig löschen|löschen/i, "Löschen"],
  [/stornieren/i, "Stornieren"],
  [/verwerfen/i, "Verwerfen"],
  [/widerrufen/i, "Widerrufen"],
  [/sperren/i, "Sperren"],
  [/zurücksetzen/i, "Zurücksetzen"],
  [/rückgängig/i, "Rückgängig machen"],
  [/archivieren/i, "Archivieren"],
  [/abmelden/i, "Abmelden"],
  [/ablehnen/i, "Ablehnen"],
  [/freistellen/i, "Freistellen"],
  [/entfernen/i, "Entfernen"],
];
const DESTRUKTIV = /löschen|stornieren|verwerfen|widerrufen|sperren|zurücksetzen|rückgängig|archivieren|ablehnen|freistellen|entfernen/i;

/** Fragt asynchron nach. Der Standardtitel und die Beschriftung der Hauptaktion
 * folgen dem Verb im Text ("... wirklich löschen?" -> "Löschen"); bei Bedarf per
 * Optionen ueberschreiben. Ohne gemounteten `BestaetigungsHost` (z. B. in Tests)
 * wird abgelehnt, statt zu haengen. */
export function bestaetigen(text: string, optionen: BestaetigungsOptionen = {}): Promise<boolean> {
  return new Promise((loesen) => {
    if (abonnenten.size === 0) {
      loesen(false);
      return;
    }
    wartend.push({ id: ++laufendeNummer, text, ...optionen, loesen });
    if (!aktuell) {
      aktuell = wartend.shift() ?? null;
      melden();
    }
  });
}

function abschliessen(ergebnis: boolean) {
  const fertig = aktuell;
  aktuell = wartend.shift() ?? null;
  melden();
  fertig?.loesen(ergebnis);
}

/** Einmal im App-Baum einhaengen (main.tsx), rendert die jeweils aktuelle Rueckfrage. */
export function BestaetigungsHost() {
  const anfrage = useSyncExternalStore(abonnieren, () => aktuell);
  if (!anfrage) return null;
  const verb = VERBEN.find(([muster]) => muster.test(anfrage.text))?.[1];
  const destruktiv = anfrage.destruktiv ?? DESTRUKTIV.test(anfrage.text);
  return (
    <BestaetigungsDialog
      key={anfrage.id}
      titel={anfrage.titel ?? (verb ? `${verb}?` : "Bitte bestätigen")}
      text={anfrage.text}
      bestaetigenLabel={anfrage.bestaetigenLabel ?? verb ?? "Bestätigen"}
      abbrechenLabel={anfrage.abbrechenLabel}
      destruktiv={destruktiv}
      onBestaetigen={() => abschliessen(true)}
      onAbbrechen={() => abschliessen(false)}
    />
  );
}
