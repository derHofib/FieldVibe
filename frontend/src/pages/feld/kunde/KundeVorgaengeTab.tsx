import { EmptyState } from "../../../components/EmptyState";
import { statusLabel } from "../../../config/vorgangDarstellung";
import type { KundeProfil, Vorgang } from "../../../types";
import { DauerauftraegeUebersicht } from "./DauerauftraegeUebersicht";
import { Inbox, Repeat } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import type { NavigateFunction } from "react-router-dom";
import { Select } from "../../../components/apple/Select";

const STATUS_BADGE: Record<string, string> = {
  neu: "border rounded-[var(--radius-ap-pill)] border-tint text-tint ",
  geplant: "border rounded-[var(--radius-ap-pill)] border-purple-400 text-purple-700 dark:border-purple-600 dark:text-purple-300",
  in_arbeit: "border rounded-[var(--radius-ap-pill)] border-st-arbeit text-st-arbeit ",
  wartet_kunde: "border rounded-[var(--radius-ap-pill)] border-st-wartet text-st-wartet",
  abgeschlossen: "border rounded-[var(--radius-ap-pill)] border-st-erledigt text-st-erledigt ",
  abgerechnet: "border rounded-[var(--radius-ap-pill)] border-sep text-label ",
  storniert: "border rounded-[var(--radius-ap-pill)] border-sep text-label2",
};

export function KundeVorgaengeTab({
  kannVerwalten,
  id,
  profil,
  anlageFilter,
  setAnlageFilter,
  sichtbareVorgaenge,
  navigate,
  anlageNameById,
}: {
  kannVerwalten: boolean;
  id: string | undefined;
  profil: KundeProfil;
  anlageFilter: string;
  setAnlageFilter: Dispatch<SetStateAction<string>>;
  sichtbareVorgaenge: Vorgang[];
  navigate: NavigateFunction;
  anlageNameById: Map<string, string>;
}) {
  return (
    <>
    {kannVerwalten && <DauerauftraegeUebersicht kundeId={id!} />}

    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-fliess font-semibold text-label2">Vorgänge</h2>
        {profil.anlagen.length > 0 && (
          <Select
            className="w-auto"
            value={anlageFilter}
            onChange={(e) => setAnlageFilter(e.target.value)}
            groesse="kompakt"
          >
            <option value="">Alle Anlagen</option>
            {profil.anlagen.map((a) => (
              <option key={a.id} value={a.id}>
                {a.bezeichnung}
              </option>
            ))}
          </Select>
        )}
      </div>
      {sichtbareVorgaenge.length === 0 ? (
        <EmptyState icon={Inbox} text="Keine Vorgänge." className="py-4" />
      ) : (
        <div className="space-y-2">
          {sichtbareVorgaenge.map((v) => (
            <button
              key={v.id}
              onClick={() => navigate(`/vorgaenge/${v.id}`)}
              className={`card-interactive btn-touch flex w-full items-center justify-between card-ap p-3 text-left ${
                v.status === "storniert" ? "opacity-60 grayscale" : ""
              }`}
            >
              <div>
                <div className="text-meta text-label2">
                  {v.vorgangsnummer}
                  {v.anlage_id && anlageNameById.get(v.anlage_id) && ` · ${anlageNameById.get(v.anlage_id)}`}
                  {v.dauerauftrag_id && (
                    <>
                      {" · "}
                      <Repeat size={11} strokeWidth={2} className="inline text-st-arbeit" />
                    </>
                  )}
                </div>
                <div className="text-fliess font-medium text-label">{v.titel}</div>
              </div>
              <span className={`px-2 py-1 text-sekundaer font-semibold ${STATUS_BADGE[v.status]}`}>
                {statusLabel(v.status)}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
    </>
  );
}
