import { Inbox } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { StatusPille } from "../../components/apple/StatusPille";
import { vorgangStatusZuToken } from "../../components/apple/status";
import { EmptyState } from "../../components/EmptyState";
import { STATUS_LABEL, istUeberfaellig } from "../../config/vorgangDarstellung";
import { useAlleSeitenLaden, useVorgangsListe } from "../../hooks/useVorgangsListe";
import type { FeedCard, VorgangStatus } from "../../types";
import { KennzahlKarte } from "../OfficeUi";

// Reihenfolge der Status-Gruppen -- Endzustaende (abgerechnet/storniert)
// zuletzt, damit die aktiven Vorgaenge oben stehen.
const STATUS_REIHENFOLGE: VorgangStatus[] = [
  "neu",
  "geplant",
  "in_arbeit",
  "wartet_kunde",
  "abgeschlossen",
  "abgerechnet",
  "storniert",
];

/** Neuer Bildschirm "Projekt-Übersicht" (siehe docs/ui-redesign/AUDIT.md,
 * Abschnitt "Wichtige Lücke"): der Auftrag beschreibt eine Projektansicht mit
 * nach Phasen gruppierten Aufträgen + offenen Positionen aus dem
 * Leistungsverzeichnis -- dafür gibt es fachlich keine Entsprechung im
 * bestehenden Datenmodell (kein "Phase"-Feld an Vorgang, keine Verknüpfung
 * zwischen Leistungsverzeichnis-Positionen und Projekt/Vertrag, siehe
 * REVIEW.md "Daten-Lücken"). Diese Übersicht baut deshalb bewusst mit dem,
 * was da ist: die per `projekt_id` verknüpften Vorgänge, gruppiert nach
 * Status statt Phase. Ergänzt (nicht ersetzt) das bestehende Asana-Kanban
 * (siehe OfficeProjektePage.tsx), das eine eigenständige, unabhängige
 * Funktion bleibt. */
export function ProjektUebersicht({ projektId }: { projektId: string }) {
  const navigate = useNavigate();
  const { data, hasNextPage, fetchNextPage, isLoading } = useVorgangsListe({ projekt_id: projektId });
  useAlleSeitenLaden(true, hasNextPage, fetchNextPage);

  const alle: FeedCard[] = data?.pages.flatMap((p) => p.items) ?? [];
  const offen = alle.filter((v) => !["abgeschlossen", "abgerechnet", "storniert"].includes(v.status));
  const ueberfaellig = alle.filter((v) => istUeberfaellig(v.faelligkeit_am));
  const erledigt = alle.filter((v) => v.status === "abgeschlossen" || v.status === "abgerechnet");

  const gruppen = STATUS_REIHENFOLGE.map((status) => ({
    status,
    vorgaenge: alle.filter((v) => v.status === status),
  })).filter((g) => g.vorgaenge.length > 0);

  if (isLoading) {
    return <p className="py-10 text-center text-sm text-label2">Lädt…</p>;
  }

  if (alle.length === 0) {
    return <EmptyState icon={Inbox} text="Noch keine Vorgänge mit diesem Projekt verknüpft." />;
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KennzahlKarte label="Vorgänge gesamt" wert={String(alle.length)} />
        <KennzahlKarte label="Offen" wert={String(offen.length)} />
        <KennzahlKarte
          label="Überfällig"
          wert={String(ueberfaellig.length)}
          ton={ueberfaellig.length > 0 ? "warnung" : "neutral"}
        />
        <KennzahlKarte label="Erledigt" wert={String(erledigt.length)} ton="gut" />
      </div>

      {gruppen.map(({ status, vorgaenge }) => (
        <div key={status}>
          <div className="mb-1.5 flex items-center gap-2 px-1">
            <StatusPille status={vorgangStatusZuToken(status)} label={STATUS_LABEL[status]} />
            <span className="text-xs text-label2">{vorgaenge.length}</span>
          </div>
          <div className="card-ap divide-y divide-sep">
            {vorgaenge.map((v) => (
              <button
                key={v.id}
                onClick={() => navigate(`/vorgaenge/${v.id}`)}
                className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left hover:bg-fill"
              >
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-semibold text-label">
                    {v.vorgangsnummer} · {v.titel}
                  </p>
                  <p className="truncate text-[11.5px] text-label2">{v.kunde_name}</p>
                </div>
                {istUeberfaellig(v.faelligkeit_am) && (
                  <span className="shrink-0 text-[11px] font-bold text-st-fehlt">überfällig</span>
                )}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
