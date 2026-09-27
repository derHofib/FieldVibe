import { ExternalLink } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
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

// Merkt sich die Listenbreite als Browser-Komfort (kein Sync noetig,
// analog zu SeitenPanel.tsx) -- gleiche Ziehgriff-Mechanik wie dort.
const LISTENBREITE_KEY = "fieldvibe_office_vorgaenge_listenbreite";
const LISTENBREITE_STANDARD = 320;
const LISTENBREITE_MIN = 260;
const LISTENBREITE_MAX = 480;

function gespeicherteListenbreite(): number {
  try {
    const roh = localStorage.getItem(LISTENBREITE_KEY);
    const wert = roh ? Number(roh) : NaN;
    if (Number.isFinite(wert) && wert >= LISTENBREITE_MIN && wert <= LISTENBREITE_MAX) return wert;
  } catch {
    // Privater Modus o.ae. -- Standardbreite reicht als Fallback.
  }
  return LISTENBREITE_STANDARD;
}

/** Liste links, Detail rechts. Das Detail-Panel rendert bewusst die
 * bestehende VorgangDetailPage (per id-Prop statt Route) statt eines
 * Nachbaus -- ein zweiter Nachbau wuerde fachlich sofort auseinanderlaufen.
 * Mit layout="dicht" bekommt sie echte Tabs statt Anker-Scroll und nutzt
 * die volle Spaltenbreite (kein max-w-3xl-Deckel mehr), waehrend die
 * mobile Feld-App und die Office-SchmaleSpalte-Route (OfficeApp.tsx)
 * unveraendert die schmale, einspaltige Fassung zeigen. Die Listenspalte
 * ist per Ziehgriff breiter/schmaler stellbar (Desktop-Erwartung), die
 * Liste per Pfeiltasten durchblaetterbar, solange kein Formularfeld den
 * Fokus haelt. */
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

  const [listenbreite, setListenbreite] = useState(gespeicherteListenbreite);
  const ziehtGerade = useRef(false);
  const aktivKarteRef = useRef<HTMLButtonElement>(null);
  const listeRef = useRef<HTMLDivElement>(null);

  // Absolute Mauspositon relativ zur linken Kante der Liste statt einer
  // beim Start erfassten Delta-Breite -- so braucht die Berechnung keinen
  // im Callback eingefrorenen Startwert (siehe SeitenPanel.tsx, gleiches
  // Prinzip mit window.innerWidth - ev.clientX).
  const ziehenStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    ziehtGerade.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    const listeLinks = listeRef.current?.getBoundingClientRect().left ?? 0;

    function aufBewegen(ev: MouseEvent) {
      if (!ziehtGerade.current) return;
      const neueBreite = Math.min(LISTENBREITE_MAX, Math.max(LISTENBREITE_MIN, ev.clientX - listeLinks));
      setListenbreite(neueBreite);
    }
    function aufLoslassen() {
      ziehtGerade.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("mousemove", aufBewegen);
      window.removeEventListener("mouseup", aufLoslassen);
      setListenbreite((aktuell) => {
        try {
          localStorage.setItem(LISTENBREITE_KEY, String(aktuell));
        } catch {
          // Kein dauerhafter Schaden, wenn das Merken der Breite fehlschlaegt.
        }
        return aktuell;
      });
    }
    window.addEventListener("mousemove", aufBewegen);
    window.addEventListener("mouseup", aufLoslassen);
  }, []);

  // Pfeiltasten-Navigation (↑/↓) durch die flach durchnummerierte Liste --
  // ignoriert Tastendruecke, solange ein Formularfeld (Suche o.ae.) den
  // Fokus haelt, sonst wuerde jeder Pfeiltastendruck beim Tippen die
  // Auswahl verschieben.
  useEffect(() => {
    function aufTaste(e: KeyboardEvent) {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const fokusTag = (e.target as HTMLElement | null)?.tagName;
      if (fokusTag === "INPUT" || fokusTag === "TEXTAREA" || fokusTag === "SELECT") return;
      if ((e.target as HTMLElement | null)?.isContentEditable) return;
      const flach = gruppen.flatMap((g) => g.cards);
      if (flach.length === 0) return;
      e.preventDefault();
      const aktuellerIndex = flach.findIndex((v) => v.id === aktiv);
      const naechsterIndex =
        e.key === "ArrowDown"
          ? Math.min(flach.length - 1, (aktuellerIndex < 0 ? -1 : aktuellerIndex) + 1)
          : Math.max(0, (aktuellerIndex < 0 ? flach.length : aktuellerIndex) - 1);
      setGewaehlt(flach[naechsterIndex].id);
    }
    document.addEventListener("keydown", aufTaste);
    return () => document.removeEventListener("keydown", aufTaste);
  }, [gruppen, aktiv]);

  useEffect(() => {
    aktivKarteRef.current?.scrollIntoView({ block: "nearest" });
  }, [aktiv]);

  return (
    <div className="flex items-start gap-0">
      {/* Karte.tsx nimmt bewusst keinen ref entgegen (kein forwardRef) --
          hier direkt als div mit derselben card-ap-Klasse, um die Breite
          fuer den Ziehgriff messen zu koennen (siehe ziehenStart oben). */}
      <div
        ref={listeRef}
        style={{ width: listenbreite }}
        className="card-ap max-h-[calc(100vh-13rem)] shrink-0 overflow-y-auto"
      >
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
                  ref={ausgewaehlt ? aktivKarteRef : undefined}
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
      </div>

      {/* Ziehgriff: 10px breiter Hit-Bereich, damit er auch ohne
          Pixel-genaues Treffen greifbar ist (siehe SeitenPanel.tsx). */}
      <div
        onMouseDown={ziehenStart}
        role="separator"
        aria-orientation="vertical"
        aria-label="Listenbreite ändern"
        className="w-[10px] shrink-0 cursor-col-resize self-stretch hover:bg-tint/20"
      />

      <Karte className="max-h-[calc(100vh-13rem)] min-w-0 flex-1 overflow-y-auto p-4">
        {aktiv ? (
          <div>
            <div className="mb-3 flex justify-end">
              <button onClick={() => navigate(`/vorgaenge/${aktiv}/vollbild`)} className="btn-ap text-xs">
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
