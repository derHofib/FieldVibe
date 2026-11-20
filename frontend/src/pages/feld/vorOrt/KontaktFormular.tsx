import { useState } from "react";

import { ApiError } from "../../../api/client";
import { Select } from "../../../components/apple/Select";
import { Feld } from "../../../components/FormularFeld";
import { FehlerMeldung } from "../../../components/Hinweiskasten";
import { type Standort, VOR_ORT_ROLLEN, VOR_ORT_ROLLE_LABEL } from "../../../types";
import { type KontaktFormWerte, pruefeKontaktForm } from "../../../utils/vorOrt";

/** Formular für einen Kontakt vor Ort (Anlegen und Ändern). Pflicht ist Name oder Telefon. */
export function KontaktFormular({
  start,
  fehler,
  laeuft,
  submitLabel,
  onSubmit,
  onAbbrechen,
  fussnote,
  standorte,
  standortBegriff = "Standort",
}: {
  start: KontaktFormWerte;
  fehler?: unknown;
  laeuft: boolean;
  submitLabel: string;
  onSubmit: (werte: KontaktFormWerte) => void;
  onAbbrechen?: () => void;
  fussnote?: string;
  /** Mit Liste erscheint eine Standort-Auswahl (Kunden-Reiter); im Ziel-Kontext fehlt sie, der Server nimmt den Standort des Ziels. */
  standorte?: Standort[];
  standortBegriff?: string;
}) {
  const [w, setW] = useState(start);
  const [pflichtFehler, setPflichtFehler] = useState<string | null>(null);
  const setze = (feld: keyof KontaktFormWerte, wert: string) => {
    setW((alt) => ({ ...alt, [feld]: wert }));
    setPflichtFehler(null);
  };
  const serverFehler = fehler ? (fehler instanceof ApiError ? fehler.message : "Speichern fehlgeschlagen") : null;

  return (
    <form
      noValidate
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        const f = pruefeKontaktForm(w);
        setPflichtFehler(f);
        if (!f) onSubmit(w);
      }}
    >
      <Feld label="Name" fehler={pflichtFehler}>
        {(p) => <input {...p} value={w.name} onChange={(e) => setze("name", e.target.value)} className="field-ap" autoComplete="off" />}
      </Feld>
      {standorte && (
        <Feld label={`${standortBegriff} (optional)`}>
          {(p) => (
            <Select {...p} value={w.standortId} onChange={(e) => setze("standortId", e.target.value)}>
              <option value="">Kein {standortBegriff}</option>
              {standorte.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.bezeichnung}
                </option>
              ))}
            </Select>
          )}
        </Feld>
      )}
      <Feld label="Rolle">
        {(p) => (
          <Select {...p} value={w.rolle} onChange={(e) => setze("rolle", e.target.value)}>
            {VOR_ORT_ROLLEN.map((r) => (
              <option key={r} value={r}>
                {VOR_ORT_ROLLE_LABEL[r]}
              </option>
            ))}
          </Select>
        )}
      </Feld>
      <Feld label="Telefon">
        {(p) => <input {...p} type="tel" value={w.telefon} onChange={(e) => setze("telefon", e.target.value)} className="field-ap" />}
      </Feld>
      <Feld label="E-Mail (optional)">
        {(p) => <input {...p} type="email" value={w.email} onChange={(e) => setze("email", e.target.value)} className="field-ap" />}
      </Feld>
      <Feld label="Einheit">
        {(p) => (
          <input
            {...p}
            value={w.einheit}
            onChange={(e) => setze("einheit", e.target.value)}
            placeholder="z. B. Whg. 3, 2. OG links"
            className="field-ap"
          />
        )}
      </Feld>
      <Feld label="Erreichbarkeit">
        {(p) => (
          <input
            {...p}
            value={w.erreichbarkeit}
            onChange={(e) => setze("erreichbarkeit", e.target.value)}
            placeholder="z. B. nachmittags"
            className="field-ap"
          />
        )}
      </Feld>
      <Feld label="Hinweis für Techniker">
        {(p) => (
          <textarea
            {...p}
            rows={2}
            value={w.hinweis}
            onChange={(e) => setze("hinweis", e.target.value)}
            placeholder="Zugang, Klingel, Schlüssel, Erreichbarkeit"
            className="field-ap"
          />
        )}
      </Feld>
      {serverFehler && <FehlerMeldung alsKasten meldung={serverFehler} />}
      {fussnote && <p className="text-sekundaer text-label2">{fussnote}</p>}
      <div className="flex justify-end gap-2">
        {onAbbrechen && (
          <button type="button" onClick={onAbbrechen} className="btn-touch btn-ap px-4 text-sekundaer">
            Abbrechen
          </button>
        )}
        <button type="submit" disabled={laeuft} className="btn-touch btn-ap-primary px-4 text-sekundaer">
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
