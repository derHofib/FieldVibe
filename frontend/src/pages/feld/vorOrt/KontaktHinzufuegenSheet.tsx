import { Plus } from "lucide-react";
import { useState } from "react";

import { GroupedList, GroupedListRow } from "../../../components/apple/GroupedList";
import { Monogramm } from "../../../components/apple/Monogramm";
import { SearchField } from "../../../components/apple/SearchField";
import { Sheet } from "../../../components/apple/Sheet";
import { FehlerMeldung } from "../../../components/Hinweiskasten";
import { SkeletonList } from "../../../components/Skeleton";
import { useDebouncedValue } from "../../../hooks/useDebouncedValue";
import { useAnonymisierungMonate, useVorOrtKontakteFuerKunde, useVorOrtZuordnen } from "../../../hooks/useVorOrt";
import type { VorOrtZiel } from "../../../types";
import {
  auswahlGruppen,
  bekanntUnterzeile,
  kontaktFormZuBody,
  kontaktAnzeigename,
  leereKontaktForm,
} from "../../../utils/vorOrt";
import { KontaktFormular } from "./KontaktFormular";
import { RollenChip } from "./KontaktZeile";

/** Auswahl bekannter Kontakte des Kunden (Standort des Ziels zuerst) oder neuer Kontakt, der gleich zugeordnet wird. */
export function KontaktHinzufuegenSheet({
  ziel,
  zielId,
  kundeId,
  standortId,
  schonZugeordnet,
  onClose,
}: {
  ziel: VorOrtZiel;
  zielId: string;
  kundeId: string;
  standortId: string | null;
  schonZugeordnet: Set<string>;
  onClose: () => void;
}) {
  const [suche, setSuche] = useState("");
  const [neu, setNeu] = useState(false);
  const q = useDebouncedValue(suche.trim());
  const { data, isLoading, isError } = useVorOrtKontakteFuerKunde(kundeId, { q: q || undefined, mit_anonymisierten: false });
  const zuordnen = useVorOrtZuordnen(ziel, zielId);
  const monate = useAnonymisierungMonate();
  const gruppen = auswahlGruppen(data ?? [], standortId, schonZugeordnet);

  const waehlen = (kontaktId: string) => zuordnen.mutate({ kontakt_id: kontaktId }, { onSuccess: onClose });

  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Kontakt vor Ort"
      links={
        <button type="button" onClick={onClose} className="text-zeile text-tint-text">
          Abbrechen
        </button>
      }
    >
      <div className="space-y-3 p-4">
        <SearchField value={suche} onChange={setSuche} placeholder="Bekannten Kontakt suchen" groesse="mobil" ariaLabel="Bekannten Kontakt suchen" />
        {isLoading ? (
          <SkeletonList count={2} />
        ) : isError ? (
          <FehlerMeldung alsKasten meldung="Kontakte konnten nicht geladen werden." />
        ) : gruppen.length === 0 ? (
          <p className="text-sekundaer text-label2">{q ? "Kein bekannter Kontakt gefunden." : "Noch keine weiteren Kontakte dieses Kunden."}</p>
        ) : (
          gruppen.map((g) => (
            <section key={g.titel ?? "rest"} aria-label={g.titel ?? "Kontakte"}>
              {g.titel && <h3 className="mb-1 px-1 text-meta font-semibold tracking-wide text-label2 uppercase">{g.titel}</h3>}
              <GroupedList>
                {g.kontakte.map((k, i) => (
                  <GroupedListRow key={k.id} onClick={() => waehlen(k.id)} last={i === g.kontakte.length - 1}>
                    <Monogramm name={kontaktAnzeigename(k)} groesse={32} ringKlasse="ring-cell" />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="text-zeile text-label">{kontaktAnzeigename(k)}</span>
                        <RollenChip rolle={k.rolle} />
                      </span>
                      {bekanntUnterzeile(k) && <span className="block text-sekundaer text-label2">{bekanntUnterzeile(k)}</span>}
                    </span>
                  </GroupedListRow>
                ))}
              </GroupedList>
            </section>
          ))
        )}
        {zuordnen.isError && !neu && <FehlerMeldung alsKasten meldung="Zuordnen fehlgeschlagen." />}

        {neu ? (
          <section aria-label="Neuen Kontakt anlegen" className="card-ap space-y-3 p-4">
            <h3 className="text-fliess font-semibold text-label">Neuen Kontakt anlegen</h3>
            <KontaktFormular
              start={leereKontaktForm()}
              laeuft={zuordnen.isPending}
              fehler={zuordnen.error}
              submitLabel="Anlegen und hinzufügen"
              onAbbrechen={() => setNeu(false)}
              onSubmit={(w) => zuordnen.mutate({ neu: kontaktFormZuBody(w) }, { onSuccess: onClose })}
              fussnote={`Wird ${monate} Monate nach dem letzten Einsatz anonymisiert.`}
            />
          </section>
        ) : (
          <button type="button" onClick={() => setNeu(true)} className="btn-touch btn-ap flex w-full items-center justify-center gap-1.5 text-sekundaer">
            <Plus size={14} strokeWidth={2.5} aria-hidden="true" /> Neuen Kontakt anlegen
          </button>
        )}
      </div>
    </Sheet>
  );
}
