import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { kundenApi } from "../../api/endpoints";
import { SearchableSelect } from "../../components/SearchableSelect";
import { EmpfaengerMitCo } from "../../components/rechnung/EmpfaengerMitCo";
import { ABSCHNITT_AKTION, Abschnitt } from "../../pages/feld/vorgang/Abschnitt";
import type { RechnungAnKurz } from "../../types";
import { RECHNUNG_AN_AUFTRAGGEBER, rechnungAnOptionen } from "../../utils/rechnungAn";

interface Props {
  auftraggeberId: string | null;
  auftraggeberName: string | null;
  rechnungAn: RechnungAnKurz | null | undefined;
  /** Speichert; `onFertig` schließt das Bearbeiten erst nach Erfolg. Leer = Auftraggeber. */
  speichern: (rechnungAnKundeId: string | null, onFertig: () => void) => void;
  laeuft: boolean;
}

/** Zeile "Rechnung an" von Auftrag und Projekt: Standard der Auftraggeber, sonst z. B. die WEG der Hausverwaltung. */
export function RechnungAnAbschnitt({ auftraggeberId, auftraggeberName, rechnungAn, speichern, laeuft }: Props) {
  const [bearbeiten, setBearbeiten] = useState(false);
  const [wahl, setWahl] = useState(RECHNUNG_AN_AUFTRAGGEBER);

  const { data: verwaltete } = useQuery({
    queryKey: ["kunden", "verwaltete", auftraggeberId],
    queryFn: () => kundenApi.verwaltete(auftraggeberId!),
    enabled: bearbeiten && !!auftraggeberId,
    retry: false,
  });
  const { data: alle } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list(), enabled: bearbeiten });

  if (!auftraggeberId) return null;

  const optionen = rechnungAnOptionen(
    auftraggeberName ? { id: auftraggeberId, name: auftraggeberName } : null,
    verwaltete ?? [],
    alle ?? [],
  );

  return (
    <Abschnitt
      titel="Abrechnung"
      aktion={
        !bearbeiten ? (
          <button
            type="button"
            onClick={() => {
              setWahl(rechnungAn?.id ?? RECHNUNG_AN_AUFTRAGGEBER);
              setBearbeiten(true);
            }}
            className={ABSCHNITT_AKTION}
          >
            Bearbeiten
          </button>
        ) : undefined
      }
    >
      {bearbeiten ? (
        <div className="space-y-2">
          <div>
            <span className="mb-1 block text-sekundaer text-label2">Rechnung an</span>
            <SearchableSelect value={wahl} onChange={setWahl} options={optionen} placeholder="Auftraggeber" />
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setBearbeiten(false)} className="btn-touch btn-ap px-3 text-sekundaer">
              Abbrechen
            </button>
            <button
              type="button"
              disabled={laeuft}
              onClick={() => speichern(wahl || null, () => setBearbeiten(false))}
              className="btn-touch btn-ap-primary px-3 text-sekundaer"
            >
              Speichern
            </button>
          </div>
        </div>
      ) : (
        <dl className="text-fliess">
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-label2">Rechnung an</dt>
            <dd className="text-right font-medium text-label">{rechnungAn ? <EmpfaengerMitCo name={rechnungAn.name} verwaltetVonName={rechnungAn.verwaltet_von_name} /> : "Auftraggeber"}</dd>
          </div>
        </dl>
      )}
    </Abschnitt>
  );
}
