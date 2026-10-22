import { useAuth } from "../../../context/AuthContext";
import { BedarfBereich } from "./BedarfBereich";
import { VerwendungenListe } from "./VerwendungenListe";
import { VerwendenFormulare } from "./VerwendenFormulare";
import type { PositionenDaten } from "./useVorgangPositionen";

interface PositionenInhaltProps {
  layout: "kompakt" | "dicht";
  positionenDaten: PositionenDaten;
}

/** Positionen-Ansicht: im dichten Layout ein Tab, im kompakten Layout die Unterseite /vorgaenge/:id/positionen. */
export function PositionenInhalt({ layout, positionenDaten }: PositionenInhaltProps) {
  const {
    angebotAusVorgangMutation, rechnungAusVorgangMutation, setShowBedarfForm, setShowLeistungForm,
    setShowMaterialForm, showBedarfForm, showLeistungForm, showMaterialForm,
  } = positionenDaten;
  const { hatRecht } = useAuth();
  const kannDisponieren = hatRecht("vorgaenge", "bearbeiten");
  return (
    <>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-heading text-sm font-semibold uppercase tracking-wide text-label">Positionen</h2>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => setShowBedarfForm((v) => !v)}
            className="btn-touch text-xs font-medium text-tint"
          >
            {showBedarfForm ? "Abbrechen" : "+ Material bestellen"}
          </button>
          <button
            onClick={() => setShowMaterialForm((v) => !v)}
            className="btn-touch text-xs font-medium text-tint"
          >
            {showMaterialForm ? "Abbrechen" : "+ Material verwenden"}
          </button>
          <button
            onClick={() => setShowLeistungForm((v) => !v)}
            className="btn-touch text-xs font-medium text-tint"
          >
            {showLeistungForm ? "Abbrechen" : "+ Leistung verwenden"}
          </button>
        </div>
      </div>

      <BedarfBereich layout={layout} positionenDaten={positionenDaten} />

      <VerwendungenListe layout={layout} positionenDaten={positionenDaten} />

      {kannDisponieren && (
        <button
          onClick={() => angebotAusVorgangMutation.mutate()}
          disabled={angebotAusVorgangMutation.isPending}
          className="btn-touch mb-2 btn-ap w-full px-3 py-1.5 text-sm"
        >
          + Angebot aus diesem Vorgang erstellen
        </button>
      )}

      {kannDisponieren && (
        <button
          onClick={() => rechnungAusVorgangMutation.mutate()}
          disabled={rechnungAusVorgangMutation.isPending}
          className="btn-touch mb-2 btn-ap w-full px-3 py-1.5 text-sm"
        >
          + Rechnung aus diesem Vorgang erstellen
        </button>
      )}

      <VerwendenFormulare positionenDaten={positionenDaten} />
    </>
  );
}
