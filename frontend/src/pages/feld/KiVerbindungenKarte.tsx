import { useState } from "react";
import { Bot } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { API_BASE_URL, ApiError } from "../../api/client";
import { kiApi } from "../../api/endpoints";
import { AbschnittskopfB } from "../../components/apple/AbschnittsKopf";
import { SymbolKachel } from "../../components/apple/SymbolKachel";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";
import { useAuth } from "../../context/AuthContext";
import { formatDatum, relativeZeit } from "../../utils/format";

/** Profilabschnitt "KI-Verbindungen" (Feld und Office). Der Aufrufer blendet ihn
 * aus, wenn das Modul `ki_zugriff` des Mandanten nicht aktiv ist. */
export function KiVerbindungenKarte() {
  const bestaetigen = useBestaetigung();
  const { currentUser } = useAuth();
  const queryClient = useQueryClient();
  const istAdmin = currentUser?.role === "mandant_admin";
  const [alle, setAlle] = useState(false);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["ki", "verbindungen", alle],
    queryFn: () => kiApi.verbindungen(alle),
  });

  const trennen = useMutation({
    mutationFn: (id: string) => kiApi.trennen(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ki", "verbindungen"] }),
  });

  async function trennenFragen(id: string, clientName: string) {
    if (
      !(await bestaetigen({
        titel: `${clientName} trennen?`,
        text: "Der Zugriff endet sofort. Zum erneuten Verbinden musst du die Einwilligung in Claude noch einmal erteilen.",
        bestaetigenLabel: "Trennen",
      }))
    ) {
      return;
    }
    trennen.mutate(id);
  }

  const connectorUrl = `${API_BASE_URL.replace(/\/+$/, "")}/mcp`;

  return (
    <section aria-labelledby="ki-verbindungen-titel">
      <div id="ki-verbindungen-titel">
        <AbschnittskopfB titel="KI-Verbindungen" />
      </div>
      <div className="card-ap space-y-3 p-4">
        {istAdmin && (
          <label className="flex items-center gap-2 text-fliess text-label">
            <input type="checkbox" checked={alle} onChange={(e) => setAlle(e.target.checked)} />
            Alle im Betrieb anzeigen
          </label>
        )}

        {isLoading ? (
          <SkeletonList count={2} />
        ) : error ? (
          <FehlerZustand fehler={error} onErneut={() => void refetch()} was="Die KI-Verbindungen" />
        ) : data && data.length > 0 ? (
          <ul className="space-y-2">
            {data.map((v) => (
              <li key={v.id} className="flex items-center gap-3 rounded-[var(--radius-ap-md)] bg-cell p-3">
                <SymbolKachel icon={Bot} farbe="indigo" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-fliess font-medium text-label">
                    {v.client_name}
                    {alle && <span className="font-normal text-label2"> · {v.user_name}</span>}
                  </p>
                  <p className="text-meta text-label2">
                    {v.scopes.includes("fieldvibe.schreiben") ? "Lesen und schreiben" : "Nur lesen"} · verbunden seit{" "}
                    {formatDatum(v.erstellt_am)} ·{" "}
                    {v.zuletzt_genutzt_am ? `zuletzt genutzt ${relativeZeit(v.zuletzt_genutzt_am)}` : "noch nicht genutzt"}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={trennen.isPending}
                  onClick={() => void trennenFragen(v.id, v.client_name)}
                  aria-label={`${v.client_name} trennen`}
                  className="btn-ap px-3 py-1.5 text-st-fehlt hover:bg-st-fehlt-bg disabled:opacity-50"
                >
                  Trennen
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <div className="space-y-2 text-sekundaer text-label2">
            <p>Keine aktive Verbindung. So verbindest du Claude mit FieldVibe:</p>
            <p>
              Füge in Claude unter „Connectors“ einen eigenen Connector mit dieser Adresse hinzu und melde dich danach
              mit deinem FieldVibe-Konto an:
            </p>
            <code className="block break-all rounded-[var(--radius-ap-sm)] bg-fill px-2 py-1.5 text-label">
              {connectorUrl}
            </code>
          </div>
        )}

        {trennen.error && (
          <p role="alert" className="text-fliess text-st-fehlt">
            {trennen.error instanceof ApiError ? trennen.error.message : "Trennen fehlgeschlagen."}
          </p>
        )}
      </div>
    </section>
  );
}
