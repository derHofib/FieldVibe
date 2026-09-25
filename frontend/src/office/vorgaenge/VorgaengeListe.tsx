import { ExternalLink } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { StatusPille } from "../../components/apple/StatusPille";
import { vorgangStatusZuToken } from "../../components/apple/status";
import {
  GRUPPEN_LABEL,
  STATUS_LABEL,
  gruppiereNachFaelligkeit,
  istUeberfaellig,
} from "../../config/vorgangDarstellung";
import { VorgangDetailPage } from "../../pages/feld/VorgangDetailPage";
import type { FeedCard } from "../../types";
import { Karte } from "../OfficeUi";

/** Liste links, Detail rechts. Das Detail-Panel rendert bewusst die
 * bestehende VorgangDetailPage (per id-Prop statt Route) statt eines
 * Nachbaus -- ein zweiter Nachbau wuerde fachlich sofort auseinanderlaufen.
 * Mit layout="dicht" bekommt sie echte Tabs statt Anker-Scroll und nutzt
 * die volle Spaltenbreite (kein max-w-3xl-Deckel mehr), waehrend die
 * mobile Feld-App und die Office-SchmaleSpalte-Route (OfficeApp.tsx)
 * unveraendert die schmale, einspaltige Fassung zeigen. */
export function VorgaengeListe({
  vorgaenge,
  hasNextPage,
  isFetchingNextPage,
  onMehr,
}: {
  vorgaenge: FeedCard[];
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  onMehr: () => void;
}) {
  const navigate = useNavigate();
  const [gewaehlt, setGewaehlt] = useState<string | null>(null);
  const aktiv = gewaehlt && vorgaenge.some((v) => v.id === gewaehlt) ? gewaehlt : vorgaenge[0]?.id;
  // Gleiche Gruppierung wie im Feed der Feld-App (siehe config/vorgangDarstellung.ts).
  const gruppen = gruppiereNachFaelligkeit(vorgaenge);

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(280px,340px)_1fr]">
      <Karte className="max-h-[calc(100vh-13rem)] overflow-y-auto">
        {gruppen.map(({ gruppe, cards }) => (
          <div key={gruppe}>
            <p className="border-b border-sep bg-fill/70 px-3 py-1 text-[10.5px] font-bold tracking-wide text-label2 uppercase">
              {GRUPPEN_LABEL[gruppe]} <span className="font-medium normal-case">{cards.length}</span>
            </p>
            {cards.map((v) => {
              const ausgewaehlt = v.id === aktiv;
              return (
                <button
                  key={v.id}
                  onClick={() => setGewaehlt(v.id)}
                  className={`block w-full border-b border-sep px-3 py-2.5 text-left last:border-b-0 ${
                    ausgewaehlt ? "border-l-2 border-l-tint bg-tintbg pl-[10px]" : "hover:bg-fill"
                  }`}
                >
                  <p className="truncate text-[13px] font-semibold text-label">
                    {v.vorgangsnummer} · {v.titel}
                  </p>
                  {/* text-label statt text-label2 im ausgewaehlten Zustand:
                   * auf bg-tintbg (helle Akzent-Flaeche) faellt text-label2
                   * bei 11.5px unter 4.5:1 Kontrast (axe-core). */}
                  <p
                    className={`mt-0.5 flex items-center gap-1.5 truncate text-[11.5px] ${ausgewaehlt ? "text-label" : "text-label2"}`}
                  >
                    <span className="truncate">{v.kunde_name}</span>
                    {istUeberfaellig(v.faelligkeit_am) && (
                      <span className="shrink-0 font-bold text-st-fehlt">· überfällig</span>
                    )}
                  </p>
                  <div className="mt-1.5">
                    <StatusPille status={vorgangStatusZuToken(v.status)} label={STATUS_LABEL[v.status]} />
                  </div>
                </button>
              );
            })}
          </div>
        ))}

        {hasNextPage && (
          <button
            onClick={onMehr}
            disabled={isFetchingNextPage}
            className="w-full py-3 text-xs font-semibold text-label2 hover:bg-fill disabled:opacity-50"
          >
            {isFetchingNextPage ? "Lädt…" : "Mehr laden"}
          </button>
        )}
      </Karte>

      <Karte className="max-h-[calc(100vh-13rem)] overflow-y-auto p-4">
        {aktiv ? (
          <div>
            <div className="mb-3 flex justify-end">
              <button onClick={() => navigate(`/vorgaenge/${aktiv}`)} className="btn-ap text-xs">
                <ExternalLink size={13} strokeWidth={2} aria-hidden="true" />
                Ganze Seite
              </button>
            </div>
            <VorgangDetailPage id={aktiv} layout="dicht" />
          </div>
        ) : (
          <p className="py-10 text-center text-sm text-label2">Links einen Vorgang auswählen.</p>
        )}
      </Karte>
    </div>
  );
}
