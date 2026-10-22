import { ZeiteintragSheet } from "../../../components/ZeiteintragSheet";
import { Sheet } from "../../../components/apple/Sheet";
import type { ZeitDaten } from "./useVorgangZeit";

interface ZeitSheetsProps {
  id: string | undefined;
  zeitDaten: ZeitDaten;
}

/** Sheets der Zeiterfassung: Eintrag anlegen/bearbeiten und Tätigkeit nach „Stoppen“. */
export function ZeitSheets({ id, zeitDaten }: ZeitSheetsProps) {
  const {
    nachStoppenEintrag, nachStoppenTaetigkeit, nachStoppenTaetigkeitMutation, setNachStoppenEintrag,
    setNachStoppenTaetigkeit, setZeitSheetModus, zeitSheetModus,
  } = zeitDaten;
  return (
    <>
      {zeitSheetModus && (
        <ZeiteintragSheet
          offen
          onClose={() => setZeitSheetModus(null)}
          vorgangId={id!}
          eintrag={zeitSheetModus === "neu" ? null : zeitSheetModus}
          onGespeichert={() => setZeitSheetModus(null)}
        />
      )}

      <Sheet
        offen={!!nachStoppenEintrag}
        onClose={() => setNachStoppenEintrag(null)}
        titel="Was hast du gemacht?"
        links={
          <button
            type="button"
            onClick={() => setNachStoppenEintrag(null)}
            className="text-[17px] text-tint"
          >
            Später
          </button>
        }
        rechts={
          <button
            type="button"
            onClick={() => nachStoppenTaetigkeitMutation.mutate()}
            disabled={!nachStoppenTaetigkeit.trim() || nachStoppenTaetigkeitMutation.isPending}
            className="text-[17px] font-semibold text-tint disabled:opacity-40"
          >
            Fertig
          </button>
        }
      >
        <div className="space-y-4 p-4">
          <input
            autoFocus
            value={nachStoppenTaetigkeit}
            onChange={(e) => setNachStoppenTaetigkeit(e.target.value)}
            placeholder="z. B. Wartung an Anlage durchgeführt"
            className="field-ap"
          />
        </div>
      </Sheet>
    </>
  );
}
