import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { notificationsApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import type { NotificationEntry } from "../../types";

function targetPath(n: NotificationEntry): string | null {
  if (n.ref_entity_type === "vorgang" && n.ref_entity_id) return `/vorgaenge/${n.ref_entity_id}`;
  if (n.ref_entity_type === "anlage" && n.ref_entity_id) return `/anlagen/${n.ref_entity_id}`;
  if (n.ref_entity_type === "eingangsrechnung" && n.ref_entity_id) return `/rechnungseingang/${n.ref_entity_id}`;
  return null;
}

export function NotificationsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data: notifications, isLoading } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => notificationsApi.list(),
  });

  const markReadMutation = useMutation({
    mutationFn: (id: number) => notificationsApi.markRead(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const markAllReadMutation = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  function handleClick(n: NotificationEntry) {
    if (n.gelesen_am === null) markReadMutation.mutate(n.id);
    const path = targetPath(n);
    if (path) navigate(path);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-ind-ink">Benachrichtigungen</h1>
        {notifications && notifications.some((n) => !n.gelesen_am) && (
          <button
            onClick={() => markAllReadMutation.mutate()}
            className="btn-touch text-sm font-medium text-blue-700 dark:text-blue-400"
          >
            Alle als gelesen markieren
          </button>
        )}
      </div>

      {isLoading ? (
        <SkeletonList count={4} />
      ) : !notifications || notifications.length === 0 ? (
        <EmptyState icon={Bell} text="Keine Benachrichtigungen." />
      ) : (
        <div className="space-y-2">
          {notifications.map((n) => (
            <button
              key={n.id}
              onClick={() => handleClick(n)}
              className={`card-interactive btn-touch flex w-full items-start justify-between rounded-lg p-3 text-left shadow-xs dark:shadow-none dark:ring-1 dark:ring-stone-800 ${
                n.gelesen_am ? "bg-white dark:bg-stone-900" : "bg-blue-50 dark:bg-blue-500/10"
              }`}
            >
              <div>
                <div className="text-sm font-medium text-ind-ink">{n.titel}</div>
                <div className="text-xs text-ind-ink-3">
                  {new Date(n.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}
                </div>
              </div>
              {!n.gelesen_am && <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-blue-600" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
