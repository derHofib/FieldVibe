import { useQuery } from "@tanstack/react-query";
import { ClipboardList } from "lucide-react";
import { useState } from "react";

import { formSubmissionsApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";
import type { FormSubmissionUebersicht } from "../../types";
import { ListeMitPanel } from "../ListeMitPanel";
import { AusgefuelltPanel } from "./AusgefuelltPanel";
import { AusgefuelltTabelle, Seitenwahl } from "./AusgefuelltTabelle";

/** Ausgefüllt-Liste einer einzelnen Vorlage (Baukasten-Tab): dieselbe Tabelle und
 * dasselbe Panel wie auf der Formulare-Seite, serverseitig auf schema_id gefiltert. */
export function AusgefuelltTab({ schemaId }: { schemaId: string }) {
  const [seite, setSeite] = useState(1);
  const [auswahl, setAuswahl] = useState<FormSubmissionUebersicht | null>(null);
  const q = useQuery({
    queryKey: ["form-submissions-uebersicht", { schema_id: schemaId }, seite],
    queryFn: () => formSubmissionsApi.uebersicht({ schema_id: schemaId, seite }),
    placeholderData: (vorher) => vorher,
  });

  if (q.isError && !q.data) return <FehlerZustand fehler={q.error} was="Die ausgefüllten Protokolle" onErneut={() => void q.refetch()} />;
  if (!q.data) return <SkeletonList count={4} />;
  if (q.data.eintraege.length === 0) {
    return <EmptyState icon={ClipboardList} text="Mit dieser Vorlage wurde noch kein Protokoll ausgefüllt." />;
  }
  return (
    <ListeMitPanel
      panelTitel="Protokoll"
      panel={auswahl ? <AusgefuelltPanel key={auswahl.id} eintrag={auswahl} /> : null}
      onSchliessen={() => setAuswahl(null)}
      liste={
        <>
          <AusgefuelltTabelle eintraege={q.data.eintraege} auswahlId={auswahl?.id ?? null} onWaehle={setAuswahl} ohneVorlage />
          <Seitenwahl seite={seite} gesamt={q.data.gesamt} anzahl={q.data.eintraege.length} onSeite={setSeite} />
        </>
      }
    />
  );
}
