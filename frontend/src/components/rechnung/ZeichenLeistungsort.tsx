import { useState } from "react";

import type { Leistungsort } from "../../types";
import {
  baueLeistungsort,
  leistungsortAdresse,
  leistungsortAlsFormular,
  leistungsortIstLeer,
  type LeistungsortFormular,
} from "../../utils/leistungsort";
import { Hinweiskasten, FehlerMeldung } from "../Hinweiskasten";

interface Props {
  kundenReferenz: string | null | undefined;
  leistungsort: Leistungsort | null | undefined;
  /** Nur im Entwurf änderbar; danach liest der Abschnitt nur und entfällt, wenn nichts gesetzt ist. */
  aenderbar: boolean;
  speichern: (body: { kunden_referenz: string | null; leistungsort: Leistungsort | null }) => Promise<unknown>;
  fehler?: string | null;
  beleg: "Rechnung" | "Angebot";
}

const ZEILE = "flex items-baseline justify-between gap-3 py-1.5";

/** Abschnitte "Empfänger" (Ihr Zeichen) und "Leistungsort" von Rechnung und Angebot. */
export function ZeichenLeistungsort({ kundenReferenz, leistungsort, aenderbar, speichern, fehler, beleg }: Props) {
  const [bearbeiten, setBearbeiten] = useState(false);
  const [zeichen, setZeichen] = useState("");
  const [form, setForm] = useState<LeistungsortFormular>(leistungsortAlsFormular(null));
  const [laeuft, setLaeuft] = useState(false);

  const hatZeichen = !!kundenReferenz;
  const hatOrt = !leistungsortIstLeer(leistungsort);
  if (!aenderbar && !hatZeichen && !hatOrt) return null;

  const start = () => {
    setZeichen(kundenReferenz ?? "");
    setForm(leistungsortAlsFormular(leistungsort));
    setBearbeiten(true);
  };
  const aendere = (teil: Partial<LeistungsortFormular>) => setForm((f) => ({ ...f, ...teil }));

  const absenden = async () => {
    setLaeuft(true);
    try {
      await speichern({ kunden_referenz: zeichen.trim() || null, leistungsort: baueLeistungsort(form, leistungsort) });
      setBearbeiten(false);
    } catch {
      // Fehlertext kommt über `fehler` der aufrufenden Seite.
    } finally {
      setLaeuft(false);
    }
  };

  const adresse = leistungsortAdresse(leistungsort);

  return (
    <div className="card-ap p-4">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-fliess font-semibold text-label2">Empfänger &amp; Leistungsort</h2>
        {aenderbar && !bearbeiten && (
          <button type="button" onClick={start} className="btn-touch text-sekundaer font-medium text-tint-text">
            Bearbeiten
          </button>
        )}
      </div>

      {bearbeiten ? (
        <div className="space-y-2">
          <label className="block text-sekundaer text-label2">
            Ihr Zeichen
            <input
              value={zeichen}
              maxLength={200}
              onChange={(e) => setZeichen(e.target.value)}
              placeholder="Bestell- bzw. Auftragsnummer des Empfängers"
              className="field-ap mt-1"
            />
          </label>
          <label className="block text-sekundaer text-label2">
            Bezeichnung
            <input
              value={form.bezeichnung}
              maxLength={200}
              onChange={(e) => aendere({ bezeichnung: e.target.value })}
              placeholder="z. B. Whg. 3, 2. OG links"
              className="field-ap mt-1"
            />
          </label>
          <label className="block text-sekundaer text-label2">
            Straße
            <input value={form.strasse} maxLength={200} onChange={(e) => aendere({ strasse: e.target.value })} className="field-ap mt-1" />
          </label>
          <div className="grid grid-cols-3 gap-2">
            <label className="block text-sekundaer text-label2">
              PLZ
              <input value={form.plz} maxLength={10} inputMode="numeric" onChange={(e) => aendere({ plz: e.target.value })} className="field-ap mt-1" />
            </label>
            <label className="col-span-2 block text-sekundaer text-label2">
              Ort
              <input value={form.ort} maxLength={100} onChange={(e) => aendere({ ort: e.target.value })} className="field-ap mt-1" />
            </label>
          </div>
          {fehler && <FehlerMeldung alsKasten meldung={fehler} />}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setBearbeiten(false)} className="btn-touch btn-ap px-3 text-sekundaer">
              Abbrechen
            </button>
            <button type="button" disabled={laeuft} onClick={() => void absenden()} className="btn-touch btn-ap-primary px-3 text-sekundaer">
              Speichern
            </button>
          </div>
        </div>
      ) : (
        <>
          <dl className="divide-y divide-sep text-fliess">
            <div className={ZEILE}>
              <dt className="text-label2">Ihr Zeichen</dt>
              <dd className="text-right font-medium text-label">{kundenReferenz || "—"}</dd>
            </div>
            <div className={ZEILE}>
              <dt className="text-label2">Bezeichnung</dt>
              <dd className="text-right font-medium text-label">{leistungsort?.bezeichnung || "—"}</dd>
            </div>
            <div className={ZEILE}>
              <dt className="text-label2">Adresse</dt>
              <dd className="text-right font-medium text-label">{adresse || "—"}</dd>
            </div>
          </dl>
          {aenderbar && (hatZeichen || hatOrt) && (
            <div className="mt-2">
              <Hinweiskasten ton="info">
                <p>
                  Aus dem Auftrag übernommen, im Entwurf änderbar. Namen von Mietern erscheinen nicht automatisch auf
                  {beleg === "Rechnung" ? " der Rechnung" : " dem Angebot"}.
                </p>
              </Hinweiskasten>
            </div>
          )}
        </>
      )}
    </div>
  );
}
