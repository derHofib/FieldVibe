import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { projektAufgabenApi } from "../../api/endpoints";
import { FehlerZustand } from "../../components/FehlerZustand";
import { DetailSkeleton } from "../../components/Skeleton";
import { Karte, SeitenKopf } from "../OfficeUi";
import { AufgabePanelHost } from "./MeineAufgabenOffice";

/** "Ganze Seite" einer Aufgabe (`/meine-aufgaben/:id`): dasselbe Panel wie im Split, nur ohne Liste daneben. */
export function MeineAufgabeSeite() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["projekt-aufgaben", "einzel", id],
    queryFn: () => projektAufgabenApi.get(id),
    enabled: !!id,
  });
  const zurueck = () => navigate("/meine-aufgaben");

  return (
    <div className="max-w-3xl">
      <SeitenKopf titel="Aufgabe" />
      {isLoading ? (
        <DetailSkeleton />
      ) : error || !data ? (
        <FehlerZustand fehler={error} was="Die Aufgabe" onErneut={() => void refetch()} />
      ) : (
        <Karte className="office-panel">
          <AufgabePanelHost aufgabe={data} onClose={zurueck} />
        </Karte>
      )}
    </div>
  );
}
