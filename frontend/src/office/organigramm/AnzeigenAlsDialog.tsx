import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { organigrammApi, usersApi } from "../../api/endpoints";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { SeitenPanel } from "../../components/apple/SeitenPanel";
import { SearchableSelect } from "../../components/SearchableSelect";
import type { AccountTyp } from "../../types";
import type { Position, RechteRegistry } from "../../types/organigramm";
import { verstaendlicherFehler } from "./darstellung";
import { EffektiveRechteTabelle } from "./EffektiveRechteTabelle";

type Modus = "user" | "position";

/** "Anzeigen als ...": effektive Rechte eines Nutzers oder einer Position -- reine Simulation, kein Accountwechsel. */
export function AnzeigenAlsDialog({
  startPositionId,
  positionen,
  registry,
  accountTypen,
  darfPersonen,
  onClose,
}: {
  startPositionId: string | null;
  positionen: Position[];
  registry: RechteRegistry | undefined;
  accountTypen: AccountTyp[];
  // Nutzer-Simulation erfordert mitarbeiterverwaltung.sehen (Backend), sonst nur Positionen anbieten
  darfPersonen: boolean;
  onClose: () => void;
}) {
  const [modus, setModus] = useState<Modus>(startPositionId || !darfPersonen ? "position" : "user");
  const [userId, setUserId] = useState("");
  const [positionId, setPositionId] = useState(startPositionId ?? "");

  const { data: users } = useQuery({ queryKey: ["users", "auswahl"], queryFn: usersApi.auswahl, enabled: darfPersonen });

  const ziel = modus === "user" ? (userId ? { user_id: userId } : null) : positionId ? { position_id: positionId } : null;
  const { data, error, isFetching } = useQuery({
    queryKey: ["org-effektiv", ziel],
    queryFn: () => organigrammApi.effektiv(ziel!),
    enabled: ziel !== null,
  });

  const positionOptionen = useMemo(
    () => positionen.filter((p) => !p.kontext).map((p) => ({ value: p.id, label: p.titel, sublabel: p.account_typ?.name })),
    [positionen],
  );
  const userOptionen = (users ?? []).filter((u) => u.aktiv).map((u) => ({ value: u.id, label: u.name, sublabel: u.account_typ_name ?? undefined }));
  const positionTitel = (id: string) => positionen.find((p) => p.id === id)?.titel;

  return (
    <SeitenPanel offen titel="Anzeigen als …" onClose={onClose} minBreite={980}>
      <div className="space-y-4 p-4">
        <p role="note" className="rounded-[10px] bg-st-arbeit-bg px-3 py-2 text-sm font-medium text-st-arbeit">
          Simulation – kein Accountwechsel. Es werden nur die Rechte angezeigt; Sie handeln weiterhin als Sie selbst.
        </p>

        {darfPersonen && (
          <SegmentedControl<Modus>
            ariaLabel="Ansicht wählen"
            optionen={[
              { wert: "user", label: "Nutzer" },
              { wert: "position", label: "Position" },
            ]}
            wert={modus}
            onChange={setModus}
          />
        )}

        <div className="max-w-md">
          <label className="mb-1 block text-sm font-medium text-label">{modus === "user" ? "Nutzer" : "Position"}</label>
          {modus === "user" ? (
            <SearchableSelect options={userOptionen} value={userId} onChange={setUserId} placeholder="Nutzer suchen…" />
          ) : (
            <SearchableSelect options={positionOptionen} value={positionId} onChange={setPositionId} placeholder="Position suchen…" />
          )}
        </div>

        {!registry ? (
          <p className="text-sm text-label2">Rechte-Registry lädt…</p>
        ) : error ? (
          <p role="alert" className="text-sm text-st-fehlt">
            {verstaendlicherFehler(error, "Effektive Rechte konnten nicht geladen werden")}
          </p>
        ) : !ziel ? (
          <p className="text-sm text-label2">Wählen Sie {modus === "user" ? "einen Nutzer" : "eine Position"}, um die effektiven Rechte zu sehen.</p>
        ) : !data || isFetching ? (
          <p className="text-sm text-label2">Lädt…</p>
        ) : (
          <>
            {data.alle_rechte && (
              <p className="text-sm text-label2">
                Die Rolle „{data.rolle}“ hat implizit alle Rechte (mandantweit), unabhängig vom Organigramm.
              </p>
            )}
            {modus === "position" && (
              <p className="text-xs text-label2">Position: Account-Typ-Vorlage plus Overrides der Position. Nutzer-Overrides sind hier nicht enthalten.</p>
            )}
            <EffektiveRechteTabelle
              registry={registry}
              daten={data}
              aufloeser={{
                accountTyp: (id) => accountTypen.find((t) => t.id === id)?.name,
                position: positionTitel,
              }}
            />
          </>
        )}
      </div>
    </SeitenPanel>
  );
}
