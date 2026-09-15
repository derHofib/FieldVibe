import { useQuery } from "@tanstack/react-query";
import { Inbox } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { kundenportalApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { STATUS_BADGE, STATUS_LABEL } from "../../config/vorgangDarstellung";

export function PortalVorgaengePage() {
  const navigate = useNavigate();
  const { data: vorgaenge, isLoading } = useQuery({
    queryKey: ["portal-vorgaenge"],
    queryFn: kundenportalApi.vorgaenge,
  });

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold text-ind-ink">Ihre Aufträge</h1>
      {isLoading ? (
        <SkeletonList count={3} />
      ) : !vorgaenge || vorgaenge.length === 0 ? (
        <EmptyState icon={Inbox} text="Keine Aufträge vorhanden." />
      ) : (
        <div className="space-y-2">
          {vorgaenge.map((v) => (
            <button
              key={v.id}
              onClick={() => navigate(`/portal/vorgaenge/${v.id}`)}
              className="card-interactive btn-touch block w-full border border-ind-line bg-ind-bg p-4 text-left"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-xs text-ind-ink-3">Auftrag Nr. {v.vorgangsnummer}</div>
                  <div className="font-medium text-ind-ink">{v.titel}</div>
                </div>
                <span className={`px-2 py-1 text-xs font-semibold ${STATUS_BADGE[v.status]}`}>
                  {STATUS_LABEL[v.status]}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
