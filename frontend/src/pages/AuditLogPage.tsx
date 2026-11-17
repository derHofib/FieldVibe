import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, CalendarDays, Building2, ScrollText } from "lucide-react";

import { auditLogApi, mandantenApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { aktivitaetLabel } from "../utils/anzeigeNamen";
import { auditLabel } from "../utils/auditLabel";
import { datumServerParameter } from "../utils/datumFilterParameter";
import { EmptyState } from "../components/EmptyState";
import { FehlerZustand } from "../components/FehlerZustand";
import { SkeletonList } from "../components/Skeleton";
import { zuServerParametern } from "../components/filter/auswerten";
import { FilterLeiste } from "../components/filter/FilterLeiste";
import type { FilterFeld } from "../components/filter/typen";
import { useFilterZustand } from "../components/filter/useFilterZustand";

type AuditZeile = Awaited<ReturnType<typeof auditLogApi.list>>[number];

export function AuditLogPage() {
  const { isImpersonating } = useAuth();

  // Beide Endpoints sind super_admin-only: ein Impersonation-Token ist als
  // mandant_admin gescoped und wuerde hier 403en -- diese Seite unmountet
  // aber ohnehin sofort, sobald die Impersonation startet (siehe App.tsx),
  // das Disablen schliesst nur das Race bis dahin (siehe MandantenPage).
  const { data: mandanten } = useQuery({
    queryKey: ["mandanten"],
    queryFn: mandantenApi.list,
    enabled: !isImpersonating,
  });

  const felder = useMemo<FilterFeld<AuditZeile>[]>(
    () => [
      {
        key: "mandant",
        label: "Mandant",
        typ: "verknuepfung",
        icon: Building2,
        operatoren: ["ist"],
        einzelwert: true,
        optionen: (mandanten ?? []).map((m) => ({ wert: m.id, label: m.name })),
      },
      { key: "aktion", label: "Aktion", typ: "text", icon: Activity, operatoren: ["enthaelt"], vorschlaege: ["login_als_mandant"] },
      { key: "zeit", label: "Zeitpunkt", typ: "datum", icon: CalendarDays, operatoren: ["am", "vor", "nach", "zwischen", "relativ"] },
    ],
    [mandanten],
  );
  const zustand = useFilterZustand({ felder });
  const serverParameter = zuServerParametern(zustand.bedingungen, {
    mandant: (b): Record<string, string> => {
      const id = Array.isArray(b.wert) ? b.wert[0] : undefined;
      return id ? { mandant_id: id } : {};
    },
    aktion: (b): Record<string, string> => (typeof b.wert === "string" && b.wert.trim() ? { aktion: b.wert.trim() } : {}),
    zeit: datumServerParameter,
  });
  const { data: entries, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["audit-log", serverParameter],
    queryFn: () => auditLogApi.list(serverParameter),
    enabled: !isImpersonating,
  });

  const mandantNameById = new Map((mandanten ?? []).map((m) => [m.id, m.name]));
  const filterAktiv = zustand.bedingungen.length > 0;
  const wirkt = (key: string) => zustand.bedingungen.some((b) => b.feld === key);

  return (
    <div>
      <FilterLeiste felder={felder} zustand={zustand} variante="office" ohneSuche className="mb-4" />

      {isLoading ? (
        <SkeletonList count={4} />
      ) : ladeFehler && !entries ? (
        <FehlerZustand fehler={ladeFehler} was="Das Protokoll" onErneut={() => void neuLaden()} />
      ) : !entries || entries.length === 0 ? (
        <EmptyState
          icon={ScrollText}
          text={
            filterAktiv
              ? "Keine Treffer für diese Filter"
              : "Noch keine Einträge im Audit-Log. Hier erscheinen Anmeldungen als Mandant und andere Plattform-Aktionen."
          }
          action={
            filterAktiv ? (
              <button type="button" onClick={zustand.zuruecksetzen} className="btn-touch btn-ap px-4">
                Filter zurücksetzen
              </button>
            ) : undefined
          }
        />
      ) : (
        <>
          <ul className="space-y-2 md:hidden">
            {entries.map((e) => (
              <li key={e.id} className="card-ap space-y-1 p-3">
                <p className="text-fliess font-medium text-label">{aktivitaetLabel(e.aktion)}</p>
                <p className="text-sekundaer text-label2">
                  {new Date(e.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}
                  {e.mandant_id ? ` · ${mandantNameById.get(e.mandant_id) ?? "–"}` : ""}
                </p>
                {e.entity_type && (
                  <p className="text-sekundaer text-label2">
                    {auditLabel(e.entity_type)} · {e.entity_id?.slice(0, 8)}
                  </p>
                )}
                {e.payload && Object.keys(e.payload).length > 0 && (
                  <p className="break-all font-mono text-sekundaer text-label2">{JSON.stringify(e.payload)}</p>
                )}
              </li>
            ))}
          </ul>
          <div className="card-ap hidden overflow-hidden md:block">
            <table className="w-full text-left">
              <thead className="bg-fill text-fliess text-label">
                <tr>
                  <th className={`px-4 py-3 ${wirkt("zeit") ? "text-tint-text" : ""}`}>Zeitpunkt</th>
                  <th className={`px-4 py-3 ${wirkt("mandant") ? "text-tint-text" : ""}`}>Mandant</th>
                  <th className={`px-4 py-3 ${wirkt("aktion") ? "text-tint-text" : ""}`}>Aktion</th>
                  <th className="px-4 py-3">Entität</th>
                  <th className="px-4 py-3">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-sep text-fliess">
                {entries.map((e) => (
                  <tr key={e.id}>
                    <td className="whitespace-nowrap px-4 py-3 text-label2">
                      {new Date(e.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}
                    </td>
                    <td className="px-4 py-3 text-label2">
                      {e.mandant_id ? mandantNameById.get(e.mandant_id) ?? "–" : "–"}
                    </td>
                    <td className="px-4 py-3 font-medium text-label">{aktivitaetLabel(e.aktion)}</td>
                    <td className="px-4 py-3 text-label2">
                      {e.entity_type ? `${auditLabel(e.entity_type)} · ${e.entity_id?.slice(0, 8)}` : "–"}
                    </td>
                    <td className="px-4 py-3 font-mono text-sekundaer text-label2">
                      {JSON.stringify(e.payload)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
