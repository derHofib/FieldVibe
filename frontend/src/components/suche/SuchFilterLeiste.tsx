import { CalendarDays, Check, ChevronDown, CircleDot, UserCheck } from "lucide-react";

import { datumZuIso } from "../../utils/format";
import type { SearchKategorie } from "../../types";
import { PulldownMenu } from "../apple/PulldownMenu";
import { formatAnzahl, KATEGORIE_INFO, kategorienLeiste } from "./kategorien";
import { type GlobaleSuche, type SuchKategorieWahl, ZEITRAUM_OPTIONEN, type Zeitraum } from "./useGlobaleSuche";

type Variante = "office" | "feld";

const HOEHE: Record<Variante, string> = {
  office: "h-7",
  // Sichtbar 32 px wie im Mockup, die Tippfläche reicht per Pseudo-Element auf 44 px.
  feld: "h-8 relative before:absolute before:inset-x-0 before:-inset-y-1.5 before:content-['']",
};

function kategorieKlasse(aktiv: boolean, variante: Variante): string {
  const basis = `inline-flex shrink-0 items-center gap-[5px] rounded-full px-2.5 text-sekundaer whitespace-nowrap ${HOEHE[variante]}`;
  if (variante === "feld") {
    return `${basis} ${aktiv ? "bg-label font-semibold text-gbg" : "bg-card font-medium text-label"}`;
  }
  return `${basis} text-label ${aktiv ? "bg-thumb font-semibold shadow-[0_1px_3px_rgba(0,0,0,.14)] dark:bg-fill2" : "font-medium"}`;
}

function pilleKlasse(aktiv: boolean, variante: Variante): string {
  const basis = `inline-flex shrink-0 items-center gap-[5px] rounded-full px-2.5 text-sekundaer whitespace-nowrap text-label ${HOEHE[variante]}`;
  if (variante === "feld") return `${basis} ${aktiv ? "bg-fill font-semibold" : "bg-card font-medium"}`;
  return `${basis} ${aktiv ? "bg-fill font-semibold" : "border-[0.5px] border-sepstrong font-medium"}`;
}

function zeitraumWert(z: Zeitraum): string {
  return typeof z === "object" ? "eigener" : z;
}

function zeitraumLabel(z: Zeitraum): string {
  if (typeof z === "object") return z.von ? `ab ${z.von.split("-").reverse().join(".")}` : "Eigener Zeitraum";
  return z === "beliebig" ? "Zeitraum" : (ZEITRAUM_OPTIONEN.find((o) => o.wert === z)?.label ?? "Zeitraum");
}

/** Kategorie-Pillen mit Trefferzahl links, die drei Filter rechts (Office) bzw. darunter (Feld). */
export function SuchFilterLeiste({
  suche,
  erlaubt,
  variante,
}: {
  suche: GlobaleSuche;
  /** Kategorien, die der Nutzer sehen darf und die auf dieser Oberfläche erreichbar sind. */
  erlaubt: SearchKategorie[];
  variante: Variante;
}) {
  const feld = variante === "feld";
  const { anzahl, kategorie, setKategorie, nurOffen, setNurOffen, zeitraum, setZeitraum, mirZugewiesen, setMirZugewiesen } = suche;
  const leiste = kategorienLeiste({ anzahl, erlaubt, gewaehlt: kategorie });
  const zahl = (k: SearchKategorie) => (anzahl?.[k] !== undefined ? formatAnzahl(anzahl[k] ?? 0) : null);
  const summe = anzahl
    ? Object.entries(anzahl)
        .filter(([k]) => erlaubt.includes(k as SearchKategorie))
        .reduce((s, [, n]) => s + (n ?? 0), 0)
    : null;

  // mouseDown abfangen: der Fokus soll im Suchfeld bleiben, damit die Tastatursteuerung weiterläuft.
  const behalteFokus = (e: React.MouseEvent) => e.preventDefault();

  const kategoriePille = (wert: SuchKategorieWahl, label: string, n: string | null) => (
    <button
      key={wert}
      type="button"
      aria-pressed={kategorie === wert}
      onMouseDown={feld ? undefined : behalteFokus}
      onClick={() => setKategorie(wert)}
      className={kategorieKlasse(kategorie === wert, variante)}
    >
      {label}
      {n !== null && <span className={`text-meta ${feld && kategorie === wert ? "opacity-70" : "font-medium text-label2"}`}>{n}</span>}
    </button>
  );

  const kategorien = (
    <div
      role="group"
      aria-label="Kategorie"
      className={`flex items-center gap-1.5 ${feld ? "scrollbar-none overflow-x-auto px-4 py-1" : "min-w-0"}`}
    >
      {kategoriePille("alle", "Alle", summe === null ? null : formatAnzahl(summe))}
      {leiste.sichtbar.map((k) => kategoriePille(k, KATEGORIE_INFO[k].plural, zahl(k)))}
      {leiste.mehr.length > 0 && (
        <PulldownMenu
          ariaLabel="Weitere Kategorien"
          items={leiste.mehr.map((k) => ({
            label: zahl(k) ? `${KATEGORIE_INFO[k].plural} · ${zahl(k)}` : KATEGORIE_INFO[k].plural,
            onSelect: () => setKategorie(k),
          }))}
          trigger={({ toggeln, triggerRef, offen }) => (
            <button
              ref={triggerRef}
              type="button"
              aria-haspopup="menu"
              aria-expanded={offen}
              onMouseDown={feld ? undefined : behalteFokus}
              onClick={toggeln}
              className={kategorieKlasse(false, variante)}
            >
              Mehr
              {anzahl && <span className="text-meta font-medium text-label2">{leiste.mehr.length}</span>}
              <ChevronDown size={13} strokeWidth={2} className="text-label2" aria-hidden="true" />
            </button>
          )}
        />
      )}
    </div>
  );

  const umschalter = (label: string, an: boolean, onToggle: () => void, Icon: typeof CircleDot) => (
    <button
      type="button"
      aria-pressed={an}
      onMouseDown={feld ? undefined : behalteFokus}
      onClick={onToggle}
      className={pilleKlasse(an, variante)}
    >
      {an ? <Check size={13} strokeWidth={2.5} aria-hidden="true" /> : <Icon size={13} strokeWidth={2} className="text-label2" aria-hidden="true" />}
      {label}
    </button>
  );

  const zeitraumAktiv = zeitraum !== "beliebig";
  const zeitraumWahl = (
    <PulldownMenu
      ariaLabel="Zeitraum"
      items={[
        ...ZEITRAUM_OPTIONEN.map((o) => ({
          label: o.label,
          aktiv: zeitraumWert(zeitraum) === o.wert,
          onSelect: () => setZeitraum(o.wert),
        })),
        {
          label: "Eigener Zeitraum …",
          aktiv: typeof zeitraum === "object",
          onSelect: () => setZeitraum({ von: datumZuIso(new Date()) }),
        },
      ]}
      trigger={({ toggeln, triggerRef, offen }) => (
        <button
          ref={triggerRef}
          type="button"
          aria-haspopup="menu"
          aria-expanded={offen}
          onMouseDown={feld ? undefined : behalteFokus}
          onClick={toggeln}
          className={pilleKlasse(zeitraumAktiv, variante)}
        >
          <CalendarDays size={13} strokeWidth={2} className={zeitraumAktiv ? "text-label" : "text-label2"} aria-hidden="true" />
          {zeitraumLabel(zeitraum)}
          <ChevronDown size={13} strokeWidth={2} className="text-label2" aria-hidden="true" />
        </button>
      )}
    />
  );

  const filter = (
    <div className={`flex items-center gap-1.5 ${feld ? "scrollbar-none overflow-x-auto px-4 py-1" : "shrink-0"}`}>
      {umschalter("Nur offene", nurOffen, () => setNurOffen(!nurOffen), CircleDot)}
      {zeitraumWahl}
      {typeof zeitraum === "object" && (
        <input
          type="date"
          aria-label="Zeitraum ab"
          value={zeitraum.von}
          onChange={(e) => setZeitraum({ von: e.target.value })}
          className={`rounded-[var(--radius-ap-input)] bg-fill px-2 text-sekundaer text-label ${feld ? "h-11 text-zeile" : "h-7"}`}
        />
      )}
      {umschalter("Mir zugewiesen", mirZugewiesen, () => setMirZugewiesen(!mirZugewiesen), UserCheck)}
    </div>
  );

  if (feld) {
    return (
      <div className="space-y-1">
        {kategorien}
        {filter}
      </div>
    );
  }
  return (
    <div className="flex items-center justify-between gap-3 overflow-hidden">
      {kategorien}
      {filter}
    </div>
  );
}
