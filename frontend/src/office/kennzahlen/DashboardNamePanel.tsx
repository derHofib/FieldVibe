import { useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { Feld, NEU_BUTTON_KLASSE } from "../../components/FormularFeld";
import { Select } from "../../components/apple/Select";
import { fehlerText } from "../../components/Toast";

// Server-Grenze für Dashboard-Namen (DashboardName in schemas/kennzahlen.py).
export const NAME_MAX = 60;

/** Name (und beim Anlegen die Startvorlage) eines Dashboards. Ein doppelter Name (409) erscheint am Feld statt als Toast. */
export function DashboardNamePanel({
  modus,
  vorlagen = [],
  anfangsName = "",
  onClose,
  onSpeichern,
}: {
  modus: "neu" | "umbenennen";
  vorlagen?: { schluessel: string; name: string }[];
  anfangsName?: string;
  onClose: () => void;
  /** Wirft bei Fehlern (z. B. ApiError 409); das Panel schließt nur nach Erfolg. */
  onSpeichern: (name: string, startMit: string) => Promise<void>;
}) {
  const [name, setName] = useState(anfangsName);
  const [startMit, setStartMit] = useState("leer");
  const [fehler, setFehler] = useState<string | null>(null);
  const [laeuft, setLaeuft] = useState(false);

  async function absenden(e: FormEvent) {
    e.preventDefault();
    const bereinigt = name.trim();
    if (!bereinigt) {
      setFehler("Bitte einen Namen eingeben.");
      return;
    }
    setLaeuft(true);
    setFehler(null);
    try {
      await onSpeichern(bereinigt, startMit);
      onClose();
    } catch (err) {
      setLaeuft(false);
      setFehler(
        err instanceof ApiError && err.status === 409
          ? "Ein Dashboard mit diesem Namen gibt es schon."
          : fehlerText(err, "Speichern fehlgeschlagen. Bitte erneut versuchen."),
      );
    }
  }

  return (
    <AnlegenPanel offen titel={modus === "neu" ? "Neues Dashboard" : "Dashboard umbenennen"} onClose={onClose}>
      <form noValidate onSubmit={(e) => void absenden(e)} className="space-y-4 p-4">
        <Feld label="Name" pflicht fehler={fehler}>
          {(p) => (
            <input
              {...p}
              type="text"
              value={name}
              maxLength={NAME_MAX}
              onChange={(e) => setName(e.target.value)}
              className="field-ap"
              autoFocus
            />
          )}
        </Feld>
        {modus === "neu" && (
          <Feld label="Starten mit">
            {(p) => (
              <Select {...p} value={startMit} onChange={(e) => setStartMit(e.target.value)}>
                <option value="leer">Leeres Dashboard</option>
                {vorlagen.map((v) => (
                  <option key={v.schluessel} value={v.schluessel}>
                    {v.name}
                  </option>
                ))}
              </Select>
            )}
          </Feld>
        )}
        <button type="submit" disabled={laeuft} className={NEU_BUTTON_KLASSE}>
          {modus === "neu" ? "Anlegen" : "Speichern"}
        </button>
      </form>
    </AnlegenPanel>
  );
}
