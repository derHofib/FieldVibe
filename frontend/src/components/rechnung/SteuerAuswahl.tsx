import { Check, ChevronDown } from "lucide-react";
import { useId, useState } from "react";
import { Link } from "react-router-dom";

import { heuteIso } from "../../utils/format";
import {
  STEUER_OPTIONEN,
  STEUER_TEXT_MAX,
  pruefe13bVoraussetzungen,
  steuerOptionLabel,
  validiereSteuer,
  type Kunde13b,
  type SteuerEingabe,
} from "../../utils/steuer";
import { GroupedList, GroupedListRow } from "../apple/GroupedList";
import { Sheet } from "../apple/Sheet";
import { Hinweiskasten } from "../Hinweiskasten";

/** Steuer einer Rechnungsposition: Auswahl der fünf Varianten (Sheet mit
 * Liste, wie die übrigen Auswahlen der Rechnungsmasken), bei "Steuerfrei" die
 * Pflichtbegründung und vorab die Hinweise zu § 12 Abs. 3 und § 13b. Reine
 * Eingabe -- gespeichert wird vom Aufrufer; das Backend prüft verbindlich. */
export function SteuerAuswahl({
  wert,
  onChange,
  kunde,
  leistungsdatum,
  disabled = false,
}: {
  wert: SteuerEingabe;
  onChange: (neu: SteuerEingabe) => void;
  /** Kunde für die 13b-Vorwarnung; solange er lädt (undefined), bleibt sie aus. */
  kunde?: (Kunde13b & { id: string }) | null;
  leistungsdatum?: string | null;
  disabled?: boolean;
}) {
  const [listeOffen, setListeOffen] = useState(false);
  const [textBesucht, setTextBesucht] = useState(false);
  const textId = useId();
  const fehler = validiereSteuer(wert);
  const probleme13b =
    wert.option === "ae_13b" && kunde ? pruefe13bVoraussetzungen(kunde, leistungsdatum, heuteIso()) : [];

  return (
    <div className="space-y-2">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setListeOffen(true)}
        aria-label={`Steuer: ${steuerOptionLabel(wert.option)}`}
        aria-haspopup="dialog"
        className="field-ap btn-touch flex items-center justify-between gap-2 text-left disabled:opacity-50"
      >
        <span className="min-w-0">{steuerOptionLabel(wert.option)}</span>
        <ChevronDown size={16} className="shrink-0 text-label3" aria-hidden="true" />
      </button>

      <Sheet
        offen={listeOffen}
        onClose={() => setListeOffen(false)}
        titel="Steuer"
        rechts={
          <button onClick={() => setListeOffen(false)} className="btn-touch text-[17px] font-semibold text-tint-text">
            Fertig
          </button>
        }
      >
        <div className="p-4">
          <GroupedList>
            {STEUER_OPTIONEN.map((o, i) => (
              <GroupedListRow
                key={o.wert}
                last={i === STEUER_OPTIONEN.length - 1}
                onClick={() => {
                  onChange({ ...wert, option: o.wert });
                  setListeOffen(false);
                }}
              >
                <span className="flex-1 text-[17px] text-label">{o.label}</span>
                {o.wert === wert.option && <Check size={18} strokeWidth={2.5} className="text-tint" aria-label="Gewählt" />}
              </GroupedListRow>
            ))}
          </GroupedList>
        </div>
      </Sheet>

      {wert.option === "e_befreit" && (
        <div>
          <label htmlFor={textId} className="mb-1 block text-xs font-medium text-label2">
            Begründung der Steuerbefreiung
          </label>
          <input
            id={textId}
            value={wert.text}
            disabled={disabled}
            maxLength={STEUER_TEXT_MAX}
            onChange={(e) => onChange({ ...wert, text: e.target.value })}
            onBlur={() => setTextBesucht(true)}
            aria-invalid={textBesucht && !!fehler}
            placeholder="z. B. Steuerfreie Ausfuhrlieferung"
            className="field-ap"
          />
          <div className="mt-1 flex justify-between gap-2 text-xs">
            {textBesucht && fehler ? <span className="text-st-fehlt">{fehler}</span> : <span />}
            <span className="shrink-0 tabular-nums text-label2">
              {wert.text.trim().length}/{STEUER_TEXT_MAX}
            </span>
          </div>
        </div>
      )}

      {wert.option === "z_pv" && (
        <Hinweiskasten ton="info">
          Nullsteuersatz nur bei Lieferung und Installation von PV-Anlagen unter den Voraussetzungen des § 12 Abs. 3
          UStG – im Zweifel mit dem Steuerberater klären.
        </Hinweiskasten>
      )}

      {probleme13b.length > 0 && kunde && (
        <Hinweiskasten ton="warnung" titel="Reverse Charge (§ 13b UStG) ist so nicht möglich">
          <ul className="list-disc space-y-0.5 pl-4">
            {probleme13b.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
          <p>
            Bitte im{" "}
            <Link to={`/kunden/${kunde.id}`} className="font-semibold underline underline-offset-2">
              Kundenprofil
            </Link>{" "}
            ergänzen. Das Speichern wird sonst vom Server abgelehnt.
          </p>
        </Hinweiskasten>
      )}
    </div>
  );
}
