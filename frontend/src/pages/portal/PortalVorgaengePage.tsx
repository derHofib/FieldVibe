import { useQuery } from "@tanstack/react-query";
import { Inbox } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { kundenportalApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import type { VorgangStatus } from "../../types";

const STATUS_LABEL: Record<VorgangStatus, string> = {
  neu: "Neu",
  geplant: "Geplant",
  in_arbeit: "In Arbeit",
  wartet_kunde: "Wartet auf Kunde",
  abgeschlossen: "Abgeschlossen",
  abgerechnet: "Abgerechnet",
  storniert: "Storniert",
};

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
                  <div className="text-xs text-ind-ink-3">{v.vorgangsnummer}</div>
                  <div className="font-medium text-ind-ink">{v.titel}</div>
                </div>
                <span className="border border-ind-line px-2 py-1 text-xs font-semibold text-ind-ink-2">
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
