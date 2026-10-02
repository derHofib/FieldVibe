import { ChevronDown, ChevronRight, Gauge, Info, Link2, MoreHorizontal, Package, Pencil, Plus, Trash2, UserPlus } from "lucide-react";
import { useRef } from "react";

import { PulldownMenu, type PulldownItem } from "../../../components/apple/PulldownMenu";
import type { ZeitplanElement, ZeitplanTyp } from "../../../types";
import { KOPF_HOEHE } from "./GanttZeitleiste";
import { ZEILEN_HOEHE, formatAbweichung, formatKurz, kritischInfo, parseTag, type Zeile } from "./zeitplanLogik";

export const LISTE_BREITE = 280;
/** Zusatzbreite der "Δ"-Spalte, solange ein Basisplan-Vergleich aktiv ist. */
export const DELTA_BREITE = 48;

const DELTA_KLASSE = { spaet: "text-st-fehlt", frueh: "text-st-erledigt", gleich: "text-label3" } as const;

const TYP_NEU_LABEL: Record<ZeitplanTyp, string> = { phase: "Phase", schritt: "Schritt", meilenstein: "Meilenstein" };

function Initialen({ name }: { name: string }) {
  const teile = name.trim().split(/\s+/);
  const kuerzel = ((teile[0]?.[0] ?? "") + (teile.length > 1 ? teile[teile.length - 1][0] : "")).toUpperCase();
  return (
    <span
      title={name}
      aria-label={`Zugewiesen an ${name}`}
      className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-fill2 text-[9px] font-semibold text-label"
    >
      {kuerzel}
    </span>
  );
}

function TitelEingabe({
  anfang,
  platzhalter,
  onFertig,
  onAbbruch,
}: {
  anfang: string;
  platzhalter?: string;
  onFertig: (titel: string) => void;
  onAbbruch: () => void;
}) {
  // Enter loest Blur-Folgeaufruf aus (Eingabe verschwindet) -- einmaliges Abschliessen sichern.
  const erledigt = useRef(false);
  function abschliessen(titel: string) {
    if (erledigt.current) return;
    erledigt.current = true;
    onFertig(titel);
  }
  return (
    <input
      autoFocus
      defaultValue={anfang}
      placeholder={platzhalter}
      aria-label="Titel"
      onFocus={(e) => e.currentTarget.select()}
      onBlur={(e) => abschliessen(e.currentTarget.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") abschliessen(e.currentTarget.value);
        if (e.key === "Escape") {
          erledigt.current = true;
          onAbbruch();
        }
      }}
      className="h-6 min-w-0 flex-1 rounded-[6px] border border-tint bg-card px-1.5 text-[13px] text-label outline-none"
    />
  );
}

/** Zweite Zeile unter dem Titel: Fremdgewerk bzw. Lieferstand. */
function zweiteZeile(e: ZeitplanElement): { text: string; warn?: boolean } | null {
  if (e.typ === "schritt" && e.partner) return { text: `Fremdgewerk · ${e.partner.name}` };
  if (e.typ === "meilenstein" && e.bestellung) {
    const lt = e.bestellung.liefertermin;
    const lieferant = e.bestellung.lieferant_name ? ` · ${e.bestellung.lieferant_name}` : "";
    return lt ? { text: `Lieferung ${formatKurz(parseTag(lt))}${lieferant}` } : { text: `Liefertermin offen${lieferant}`, warn: true };
  }
  return null;
}

/** Linke Spalte: Phasen als aufklappbare Gruppen, darunter Schritte und
 * Meilensteine; inline anlegen und umbenennen. */
export function GanttListe({
  zeilen,
  eingeklappt,
  bearbeiteId,
  kritischModus,
  vergleich,
  onToggle,
  onBearbeiteStart,
  onUmbenennen,
  onBearbeiteEnde,
  onEntwurfStart,
  onEntwurfFertig,
  onFortschritt,
  onZuweisen,
  onDetails,
  onLoeschen,
}: {
  zeilen: Zeile[];
  eingeklappt: Set<string>;
  bearbeiteId: string | null;
  kritischModus: boolean;
  /** Basisplan-Vergleich aktiv: schmale Spalte "Δ" rechts. */
  vergleich: boolean;
  onToggle: (phaseId: string) => void;
  onBearbeiteStart: (id: string) => void;
  onUmbenennen: (id: string, titel: string) => void;
  onBearbeiteEnde: () => void;
  onEntwurfStart: (typ: ZeitplanTyp, phaseId: string | null) => void;
  onEntwurfFertig: (typ: ZeitplanTyp, phaseId: string | null, titel: string | null) => void;
  onFortschritt: (e: ZeitplanElement) => void;
  onZuweisen: (e: ZeitplanElement) => void;
  onDetails: (e: ZeitplanElement) => void;
  onLoeschen: (e: ZeitplanElement) => void;
}) {
  // Einfachklick oeffnet die Details; ein Doppelklick (Umbenennen) soll sie
  // nicht vorher oeffnen -- daher kurz warten und beim zweiten Klick abbrechen.
  const klickTimer = useRef<number | null>(null);
  function einfachKlick(e: ZeitplanElement) {
    if (klickTimer.current !== null) window.clearTimeout(klickTimer.current);
    klickTimer.current = window.setTimeout(() => {
      klickTimer.current = null;
      onDetails(e);
    }, 220);
  }
  function doppelKlick(e: ZeitplanElement) {
    if (klickTimer.current !== null) window.clearTimeout(klickTimer.current);
    klickTimer.current = null;
    onBearbeiteStart(e.id);
  }

  function menue(e: ZeitplanElement): PulldownItem[] {
    return [
      { label: "Details …", icon: Info, onSelect: () => onDetails(e) },
      { label: "Umbenennen", icon: Pencil, onSelect: () => onBearbeiteStart(e.id) },
      ...(e.typ === "schritt" ? [{ label: "Fortschritt setzen …", icon: Gauge, onSelect: () => onFortschritt(e) }] : []),
      { label: "Zuweisen …", icon: UserPlus, onSelect: () => onZuweisen(e) },
      "trenner" as const,
      { label: "Löschen …", icon: Trash2, onSelect: () => onLoeschen(e) },
    ];
  }

  return (
    <div className="sticky left-0 z-20 shrink-0 bg-card" style={{ width: LISTE_BREITE + (vergleich ? DELTA_BREITE : 0) }}>
      <div className="sticky top-0 z-10 flex items-end bg-card px-3 pb-1.5" style={{ height: KOPF_HOEHE }}>
        <span className="flex-1 text-[11px] font-bold tracking-wide text-label3 uppercase">Phasen &amp; Schritte</span>
        {vergleich && (
          <span className="text-right text-[11px] font-bold text-label3" style={{ width: DELTA_BREITE - 12 }} title="Abweichung zum Basisplan in Tagen (positiv = später)">
            Δ
          </span>
        )}
      </div>
      {zeilen.map((z, i) => {
        const stil = { height: ZEILEN_HOEHE };
        if (z.art === "entwurf") {
          return (
            <div key={`entwurf-${i}`} className="flex items-center gap-1.5 pr-2" style={{ ...stil, paddingLeft: z.phaseId ? 32 : 12 }}>
              <TitelEingabe
                anfang=""
                platzhalter={`Name der neuen ${TYP_NEU_LABEL[z.typ]}`}
                onFertig={(t) => onEntwurfFertig(z.typ, z.phaseId, t.trim() || null)}
                onAbbruch={() => onEntwurfFertig(z.typ, z.phaseId, null)}
              />
            </div>
          );
        }
        if (z.art === "neu") {
          const typen: ZeitplanTyp[] = z.phaseId ? ["schritt", "meilenstein"] : ["phase", "schritt", "meilenstein"];
          return (
            <div key={`neu-${z.phaseId ?? "fuss"}`} className="flex items-center gap-0.5" style={{ ...stil, paddingLeft: z.phaseId ? 26 : 6 }}>
              {typen.map((typ) => (
                <button
                  key={typ}
                  type="button"
                  onClick={() => onEntwurfStart(typ, z.phaseId)}
                  className="flex h-6 items-center gap-0.5 rounded-[6px] px-1.5 text-xs font-medium text-tint-text hover:bg-fill"
                >
                  <Plus size={13} strokeWidth={2} aria-hidden="true" />
                  {TYP_NEU_LABEL[typ]}
                </button>
              ))}
            </div>
          );
        }

        const e = z.element;
        const istPhase = e.typ === "phase";
        const zugeklappt = eingeklappt.has(e.id);
        const kritischHervor = kritischModus && e.kritisch;
        const kritischText = kritischModus ? kritischInfo(e) : null;
        const abweichung = vergleich ? formatAbweichung(e.abweichung_tage) : null;
        return (
          <div
            key={e.id}
            className={`group flex items-center gap-1.5 pr-1.5 ${istPhase ? "bg-fill" : ""}`}
            style={{ ...stil, paddingLeft: istPhase ? 6 : 26 }}
          >
            {istPhase ? (
              <button
                type="button"
                onClick={() => onToggle(e.id)}
                aria-expanded={!zugeklappt}
                aria-label={`${e.titel} ${zugeklappt ? "aufklappen" : "zuklappen"}`}
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-[6px] text-label2 hover:bg-fill2"
              >
                {zugeklappt ? <ChevronRight size={15} strokeWidth={2} /> : <ChevronDown size={15} strokeWidth={2} />}
              </button>
            ) : e.typ === "meilenstein" ? (
              <span aria-hidden="true" className={`mx-1 h-2.5 w-2.5 shrink-0 rotate-45 ${kritischHervor ? "bg-st-fehlt-dot" : "bg-tone-amber"}`} />
            ) : (
              <span aria-hidden="true" className={`h-2.5 w-3.5 shrink-0 rounded-[3px] ${kritischHervor ? "bg-st-fehlt-dot" : "bg-tint-solid"}`} />
            )}

            {bearbeiteId === e.id ? (
              <TitelEingabe
                anfang={e.titel}
                onFertig={(t) => {
                  const titel = t.trim();
                  if (titel && titel !== e.titel) onUmbenennen(e.id, titel);
                  onBearbeiteEnde();
                }}
                onAbbruch={onBearbeiteEnde}
              />
            ) : (
              <button
                type="button"
                onClick={() => einfachKlick(e)}
                onDoubleClick={() => doppelKlick(e)}
                title={`${e.titel} – Details öffnen${kritischText ? `\n${kritischText}` : ""}`}
                className="flex min-w-0 flex-1 flex-col items-start text-left"
              >
                <span
                  className={`flex w-full min-w-0 items-center gap-1 text-[13px] leading-[16px] ${istPhase ? "font-semibold" : ""} ${
                    e.erledigt ? "text-label2 line-through" : "text-label"
                  }`}
                >
                  <span className="truncate">{e.titel}</span>
                  {e.vorgang && <Link2 size={12} strokeWidth={2} className="shrink-0 text-label2" aria-label={`Vorgang ${e.vorgang.vorgangsnummer} verknüpft`} role="img" />}
                  {e.bestellung && <Package size={12} strokeWidth={2} className="shrink-0 text-label2" aria-label={`Bestellung ${e.bestellung.bestellnummer} verknüpft`} role="img" />}
                </span>
                {kritischText && !zweiteZeile(e) && (
                  <span className={`block w-full truncate text-[11px] leading-[12px] ${kritischHervor ? "text-st-fehlt" : "text-label2"}`}>{kritischText}</span>
                )}
                {zweiteZeile(e) && (
                  <span className={`block w-full truncate text-[11px] leading-[12px] ${zweiteZeile(e)!.warn ? "text-st-arbeit" : "text-label2"}`}>
                    {zweiteZeile(e)!.text}
                  </span>
                )}
              </button>
            )}

            {e.zugewiesen_name && <Initialen name={e.zugewiesen_name} />}
            <PulldownMenu
              ariaLabel={`Aktionen für ${e.titel}`}
              items={menue(e)}
              trigger={({ offen, toggeln, triggerRef }) => (
                <button
                  ref={triggerRef}
                  type="button"
                  onClick={toggeln}
                  aria-haspopup="menu"
                  aria-expanded={offen}
                  aria-label={`Aktionen für ${e.titel}`}
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-[6px] text-label2 hover:bg-fill2 focus-visible:opacity-100 group-hover:opacity-100 ${
                    offen ? "opacity-100" : "opacity-0"
                  }`}
                >
                  <MoreHorizontal size={15} strokeWidth={2} aria-hidden="true" />
                </button>
              )}
            />
            {vergleich && (
              <span
                className={`shrink-0 text-right text-[12px] font-semibold tabular-nums ${abweichung ? DELTA_KLASSE[abweichung.ton] : "text-label3"}`}
                style={{ width: DELTA_BREITE - 12 }}
                aria-label={abweichung ? `Abweichung zum Basisplan ${abweichung.text}` : "Kein Basisplan-Eintrag"}
              >
                {abweichung?.text ?? "–"}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
