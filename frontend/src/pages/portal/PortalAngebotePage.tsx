import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { kundenportalApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { ANGEBOT_STATUS_BADGE, ANGEBOT_STATUS_LABEL } from "./status";

export function PortalAngebotePage() {
  const navigate = useNavigate();
  const { data: angebote, isLoading } = useQuery({
    queryKey: ["portal-angebote"],
    queryFn: kundenportalApi.angebote,
  });

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold text-label">Ihre Angebote</h1>
      {isLoading ? (
        <SkeletonList count={3} />
      ) : !angebote || angebote.length === 0 ? (
        <EmptyState icon={FileText} text="Keine Angebote vorhanden." />
      ) : (
        <div className="space-y-2">
          {angebote.map((a) => (
            <button
              key={a.id}
              onClick={() => navigate(`/portal/angebote/${a.id}`)}
              className="card-interactive btn-touch block w-full card-ap p-4 text-left"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-xs text-label2">Angebot Nr. {a.angebotsnummer}</div>
                  <div className="font-medium text-label">{a.gesamt_brutto} EUR</div>
                </div>
                <span className={`px-2 py-1 text-xs font-semibold ${ANGEBOT_STATUS_BADGE[a.status]}`}>
                  {ANGEBOT_STATUS_LABEL[a.status]}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
