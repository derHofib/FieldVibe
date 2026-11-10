import { Check, Copy, Download } from "lucide-react";
import { useState } from "react";

import { Hinweiskasten } from "./Hinweiskasten";

/** Vollbild-Anzeige der Wiederherstellungscodes. Die Codes sind nach dem
 * Schließen nicht mehr abrufbar (serverseitig nur gehasht) -- deshalb muss
 * das Speichern ausdrücklich bestätigt werden. */
export function MfaCodesAnzeige({ codes, onFertig }: { codes: string[]; onFertig: () => void }) {
  const [gespeichert, setGespeichert] = useState(false);
  const [kopiert, setKopiert] = useState(false);
  const text = codes.join("\n");

  async function kopieren() {
    try {
      await navigator.clipboard.writeText(text);
      setKopiert(true);
    } catch {
      /* Zwischenablage nicht verfügbar: Codes bleiben markierbar sichtbar */
    }
  }

  function herunterladen() {
    const url = URL.createObjectURL(new Blob([`FieldVibe Wiederherstellungscodes\n\n${text}\n`], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "fieldvibe-wiederherstellungscodes.txt";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="mfa-codes-titel"
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-gbg p-4"
    >
      <div className="card-ap w-full max-w-md space-y-4 p-5">
        <h1 id="mfa-codes-titel" className="text-[17px] font-semibold text-label">
          Wiederherstellungscodes
        </h1>
        <Hinweiskasten ton="warnung" titel="Jetzt sichern – sie werden nur einmal angezeigt">
          Jeder Code funktioniert genau einmal, falls du dein Handy verlierst. Bewahre sie getrennt vom Handy auf
          (Passwort-Manager oder Ausdruck).
        </Hinweiskasten>
        <ul className="grid grid-cols-2 gap-2 font-mono text-sm text-label" aria-label="Wiederherstellungscodes">
          {codes.map((c) => (
            <li key={c} className="rounded-[var(--radius-ap-input)] bg-fill px-2 py-1.5 text-center select-all">
              {c}
            </li>
          ))}
        </ul>
        <div className="flex gap-2">
          <button type="button" onClick={kopieren} className="btn-touch btn-ap flex flex-1 items-center justify-center gap-2">
            {kopiert ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
            {kopiert ? "Kopiert" : "Kopieren"}
          </button>
          <button type="button" onClick={herunterladen} className="btn-touch btn-ap flex flex-1 items-center justify-center gap-2">
            <Download size={16} aria-hidden="true" /> Herunterladen
          </button>
        </div>
        <label className="flex items-start gap-2 text-sm text-label">
          <input
            type="checkbox"
            checked={gespeichert}
            onChange={(e) => setGespeichert(e.target.checked)}
            className="mt-0.5"
          />
          Ich habe die Codes sicher gespeichert.
        </label>
        <button
          type="button"
          disabled={!gespeichert}
          onClick={onFertig}
          className="btn-touch btn-ap-primary w-full py-2 disabled:opacity-50"
        >
          Fertig
        </button>
      </div>
    </div>
  );
}
