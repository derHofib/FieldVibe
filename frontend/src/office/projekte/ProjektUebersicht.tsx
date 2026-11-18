import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { projekteApi } from "../../api/endpoints";
import { AuftraegeUndVorgaenge, ProjektKennzahlen, useProjektInhalt } from "./AuftraegeUndVorgaenge";

/** Ansicht "Übersicht" der Projekte-Seite für ein Projekt: Kennzahlen und der Abschnitt "Aufträge und
 * Vorgänge" (derselbe wie im Detail-Panel). Ersetzt die frühere Gruppierung nach Status, die Aufträge
 * nicht kannte. Projektphasen gibt es im Datenmodell nicht (siehe docs/ui-redesign/REVIEW.md). */
export function ProjektUebersicht({ projektId }: { projektId: string }) {
  const navigate = useNavigate();
  const { data: projekt } = useQuery({ queryKey: ["projekte", projektId], queryFn: () => projekteApi.get(projektId) });
  const { auftraege, vorgaenge, laedt } = useProjektInhalt(projektId);

  return (
    <div className="space-y-4">
      {projekt && <ProjektKennzahlen projekt={projekt} auftraege={auftraege} vorgaenge={vorgaenge} />}
      <AuftraegeUndVorgaenge projektId={projektId} auftraege={auftraege} vorgaenge={vorgaenge} laedt={laedt} navigate={navigate} />
    </div>
  );
}
