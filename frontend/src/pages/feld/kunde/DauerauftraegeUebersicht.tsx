import { useQuery } from "@tanstack/react-query";
import { Repeat } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { dauerauftraegeApi } from "../../../api/endpoints";
import { NEU_BUTTON_KLASSE } from "../../../components/FormularFeld";
import { EmptyState } from "../../../components/EmptyState";

export function DauerauftraegeUebersicht({ kundeId }: { kundeId: string }) {
  const navigate = useNavigate();
  const { data: dauerauftraege } = useQuery({
    queryKey: ["dauerauftraege", kundeId],
    queryFn: () => dauerauftraegeApi.list(kundeId),
  });

  return (
    <div>
      <h2 className="mb-2 text-fliess font-semibold text-label2">Dauer-Aufträge</h2>
      {!dauerauftraege || dauerauftraege.length === 0 ? (
        <EmptyState icon={Repeat} text="Keine Dauer-Aufträge." className="py-4" />
      ) : (
        <div className="space-y-2">
          {dauerauftraege.map((d) => (
            <button
              key={d.id}
              onClick={() => navigate(`/dauerauftraege/${d.id}`)}
              className="card-interactive btn-touch flex w-full items-center justify-between card-ap p-3 text-left"
            >
              <div>
                <div className="text-fliess font-medium text-label">
                  {d.titel}
                  {d.anzahl_ziele > 1 && (
                    <span className="ml-2 border rounded-[var(--radius-ap-pill)] border-sep px-2 py-0.5 text-meta font-normal text-label">
                      {d.anzahl_ziele} Anlagen
                    </span>
                  )}
                </div>
                <div className="text-sekundaer text-label2">
                  alle {d.intervall_tage} Tage
                  {d.naechste_faelligkeit_am && ` · nächste Fälligkeit ${d.naechste_faelligkeit_am}`}
                </div>
              </div>
              {!d.aktiv && (
                <span className="border rounded-[var(--radius-ap-pill)] border-sep px-2 py-1 text-sekundaer text-label">
                  pausiert
                </span>
              )}
            </button>
          ))}
        </div>
      )}
      <button
        onClick={() => navigate(`/dauerauftraege/neu?kunde_id=${kundeId}`)}
        className={`${NEU_BUTTON_KLASSE} mt-2`}
      >
        + Neuer Dauerauftrag
      </button>
    </div>
  );
}
