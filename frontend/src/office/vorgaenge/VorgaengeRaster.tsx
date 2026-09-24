import { useQueryClient, useMutation } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { vorgaengeApi } from "../../api/endpoints";
import { StatusPille } from "../../components/apple/StatusPille";
import { vorgangStatusZuToken } from "../../components/apple/status";
import {
  GRUPPEN_LABEL,
  STATUS_LABEL,
  gruppiereNachFaelligkeit,
  istUeberfaellig,
} from "../../config/vorgangDarstellung";
import type { FeedCard } from "../../types";
import { Karte } from "../OfficeUi";

/** Dichtes Raster mit Mehrfachauswahl. Der eigentliche Gewinn gegenueber der
 * Liste ist die Sammelaktion -- am Handy gibt es dafuer keinen Bedarf, am
 * Schreibtisch schon (20 Vorgaenge auf einmal einem Techniker zuweisen). */
export function VorgaengeRaster({ vorgaenge }: { vorgaenge: FeedCard[] }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [ausgewaehlt, setAusgewaehlt] = useState<Set<string>>(new Set());
  const [fokus, setFokus] = useState(0);

  // Gleiche Gruppierung wie im Feed der Feld-App (siehe
  // config/vorgangDarstellung.ts) -- j/k/x/Enter navigieren ueber die so
  // entstandene, umsortierte Reihenfolge, nicht ueber die urspruengliche
  // Server-Reihenfolge.
  const gruppen = gruppiereNachFaelligkeit(vorgaenge);
  const geordnete = gruppen.flatMap((g) => g.cards);

  // Auswahl bereinigen, wenn ein Vorgang durch Filterwechsel verschwindet --
  // sonst wuerde eine Sammelaktion unsichtbare Vorgaenge mitaendern.
  useEffect(() => {
    setAusgewaehlt((alt) => {
      const sichtbar = new Set(vorgaenge.map((v) => v.id));
      const neu = new Set([...alt].filter((id) => sichtbar.has(id)));
      return neu.size === alt.size ? alt : neu;
    });
  }, [vorgaenge]);

  const umschalten = (id: string) =>
    setAusgewaehlt((alt) => {
      const neu = new Set(alt);
      if (neu.has(id)) neu.delete(id);
      else neu.add(id);
      return neu;
    });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const ziel = e.target as HTMLElement | null;
      if (ziel && (ziel.tagName === "INPUT" || ziel.tagName === "TEXTAREA")) return;
      if (e.key === "j") setFokus((f) => Math.min(geordnete.length - 1, f + 1));
      else if (e.key === "k") setFokus((f) => Math.max(0, f - 1));
      else if (e.key === "x" && geordnete[fokus]) {
        e.preventDefault();
        umschalten(geordnete[fokus].id);
      } else if (e.key === "Enter" && geordnete[fokus]) {
        navigate(`/vorgaenge/${geordnete[fokus].id}`);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [geordnete, fokus, navigate]);

  const statusSetzen = useMutation({
    mutationFn: async (status: "geplant" | "in_arbeit") => {
      for (const id of ausgewaehlt) {
        await vorgaengeApi.update(id, { status });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      setAusgewaehlt(new Set());
    },
  });

  return (
    <div>
      {ausgewaehlt.size > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl bg-tintbg px-3 py-2 text-xs font-semibold text-tint">
          <span>{ausgewaehlt.size} ausgewählt</span>
          <button onClick={() => statusSetzen.mutate("geplant")} disabled={statusSetzen.isPending} className="btn-ap text-xs">
            Auf „Geplant" setzen
          </button>
          <button onClick={() => statusSetzen.mutate("in_arbeit")} disabled={statusSetzen.isPending} className="btn-ap text-xs">
            Auf „In Arbeit" setzen
          </button>
          <button
            onClick={() => setAusgewaehlt(new Set())}
            className="rounded-lg px-2 py-1 font-medium opacity-70"
          >
            Auswahl aufheben
          </button>
          <span className="ml-auto font-medium text-label2">
            Auswählen mit <Taste>x</Taste> · navigieren mit <Taste>j</Taste> <Taste>k</Taste> ·
            öffnen mit <Taste>Enter</Taste>
          </span>
        </div>
      )}

      {(() => {
        let laufindex = -1;
        return gruppen.map(({ gruppe, cards }) => (
          <div key={gruppe} className="mb-4 last:mb-0">
            <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold tracking-wide text-label3 uppercase">
              {GRUPPEN_LABEL[gruppe]}
              <span className="font-medium normal-case text-label2">{cards.length}</span>
            </p>
            <div className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-3">
              {cards.map((v) => {
                laufindex++;
                const index = laufindex;
                const gewaehlt = ausgewaehlt.has(v.id);
                const ueberfaellig = istUeberfaellig(v.faelligkeit_am);
                return (
                  <Karte
                    key={v.id}
                    className="relative p-3"
                    // .card-ap setzt Rand/Schatten als CSS-Shorthand ausserhalb
                    // jedes @layer -- Tailwind-Utilities (border-*/ring-*, im
                    // "utilities"-Layer) koennten das nie ueberschreiben,
                    // deshalb Auswahl-/Fokus-Ring hier per Inline-Style.
                    style={{
                      borderColor: gewaehlt ? "var(--tint)" : undefined,
                      boxShadow: gewaehlt
                        ? "0 0 0 1px var(--tint)"
                        : index === fokus
                          ? "0 0 0 1px var(--sepstrong)"
                          : undefined,
                    }}
                  >
                    <button
                      onClick={() => umschalten(v.id)}
                      aria-label={gewaehlt ? "Abwählen" : "Auswählen"}
                      aria-pressed={gewaehlt}
                      className={`absolute top-2.5 right-2.5 flex h-4 w-4 items-center justify-center rounded border ${
                        gewaehlt ? "border-tint bg-tint text-white" : "border-sepstrong"
                      }`}
                    >
                      {gewaehlt && <Check size={11} strokeWidth={3} aria-hidden="true" />}
                    </button>

                    <button onClick={() => navigate(`/vorgaenge/${v.id}`)} className="block w-full text-left">
                      <p className="text-[10px] font-bold text-label2">
                        {v.vorgangsnummer}
                      </p>
                      <p className="mt-0.5 pr-5 text-[13px] font-semibold text-label">
                        {v.titel}
                      </p>
                      <div className="mt-2 flex items-center justify-between gap-2">
                        <span className="truncate text-[11px] text-label2">
                          {v.kunde_name}
                        </span>
                        {ueberfaellig ? (
                          <span className="shrink-0 rounded-full bg-st-fehlt-bg px-2 py-0.5 text-[10px] font-semibold text-st-fehlt">
                            Überfällig
                          </span>
                        ) : (
                          <StatusPille status={vorgangStatusZuToken(v.status)} label={STATUS_LABEL[v.status]} />
                        )}
                      </div>
                    </button>
                  </Karte>
                );
              })}
            </div>
          </div>
        ));
      })()}
    </div>
  );
}

function Taste({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-b-2 border-sepstrong bg-fill px-1 text-[10px] font-bold text-label2">
      {children}
    </kbd>
  );
}
