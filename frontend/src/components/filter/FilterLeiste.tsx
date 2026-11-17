import { Bookmark, ChevronDown, Funnel, FunnelPlus, X } from "lucide-react";
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";

import { istOfficeHost } from "../../office/hostname";
import type { GespeicherterFilterEntitaet } from "../../types";
import { SearchField } from "../apple/SearchField";
import { Sheet } from "../apple/Sheet";
import { AnsichtenListeFeld, AnsichtenMenue } from "./AnsichtenMenue";
import { pillenTeile } from "./auswerten";
import { EntwurfsPille, FilterPille, type PillenTeile } from "./FilterPille";
import { Kopf, Liste, type Variante } from "./FilterListe";
import { FilterPopover, PopoverRahmen } from "./FilterPopover";
import { OperatorSchritt, SpaltenSchritt, WertSchritt } from "./FilterSchritte";
import { OPERATOR_LABEL, type FilterBedingung, type FilterFeld } from "./typen";
import { useAnsichten } from "./useAnsichten";
import { useFilterEntwurf } from "./useFilterEntwurf";
import type { FilterZustand } from "./useFilterZustand";

const LUECKE = 6;
const PLUS_BREITE = 28;

export interface FilterLeisteProps<T> {
  felder: FilterFeld<T>[];
  zustand: FilterZustand;
  suchPlatzhalter?: string;
  ansichten?: GespeicherterFilterEntitaet;
  alteVorlageUmrechnen?: (alt: Record<string, string>) => FilterBedingung[];
  variante?: Variante;
  ohneSuche?: boolean;
  className?: string;
}

interface PillenEintrag {
  b: FilterBedingung;
  index: number;
  teile: PillenTeile;
}

/** Die eine Filterzeile, die Seiten einbinden: Suche + Pillen + Anlegen-Ablauf + Ansichten.
 * Office: einreihige Leiste mit Popover; Feld: Suchfeld, scrollbare Pillenreihe und Sheet. */
export function FilterLeiste<T>(props: FilterLeisteProps<T>) {
  const { felder, zustand, suchPlatzhalter = "Suchen…", ansichten, alteVorlageUmrechnen, ohneSuche = false, className = "" } = props;
  const variante: Variante = props.variante ?? (istOfficeHost() ? "office" : "feld");
  const e = useFilterEntwurf(felder, zustand);
  const a = useAnsichten({ entitaet: ansichten, zustand, felder, alteVorlageUmrechnen });
  const [anker, setAnker] = useState<HTMLElement | null>(null);

  const eintraege: PillenEintrag[] = useMemo(
    () =>
      zustand.bedingungen.flatMap((b, index) => {
        const feld = felder.find((f) => f.key === b.feld);
        return feld ? [{ b, index, teile: pillenTeile(b, feld) }] : [];
      }),
    [zustand.bedingungen, felder],
  );
  const n = eintraege.length;

  const live = (
    <div aria-live="polite" className="sr-only">
      {n > 0 ? `${n} Filter aktiv` : "Keine Filter aktiv"}
    </div>
  );

  if (variante === "feld") {
    return (
      <FeldLeiste
        {...{ felder, zustand, suchPlatzhalter, ansichten, ohneSuche, className, e, a, eintraege }}
        live={live}
      />
    );
  }
  return (
    <OfficeLeiste
      {...{ felder, zustand, suchPlatzhalter, ansichten, ohneSuche, className, e, a, eintraege, anker, setAnker }}
      live={live}
    />
  );
}

type Gemeinsam<T> = {
  felder: FilterFeld<T>[];
  zustand: FilterZustand;
  suchPlatzhalter: string;
  ansichten?: GespeicherterFilterEntitaet;
  ohneSuche: boolean;
  className: string;
  e: ReturnType<typeof useFilterEntwurf<T>>;
  a: ReturnType<typeof useAnsichten<T>>;
  eintraege: PillenEintrag[];
  live: React.ReactNode;
};

function OfficeLeiste<T>({
  felder,
  zustand,
  suchPlatzhalter,
  ansichten,
  ohneSuche,
  className,
  e,
  a,
  eintraege,
  live,
  anker,
  setAnker,
}: Gemeinsam<T> & { anker: HTMLElement | null; setAnker: (el: HTMLElement | null) => void }) {
  const n = eintraege.length;
  const [alleOffen, setAlleOffen] = useState(false);
  const [passend, setPassend] = useState(n);
  const bereichRef = useRef<HTMLDivElement>(null);
  const messRef = useRef<HTMLDivElement>(null);
  const signatur = eintraege.map((x) => `${x.teile.spalte}|${x.teile.operator}|${x.teile.wert}`).join("\n");

  const messen = useCallback(() => {
    const bereich = bereichRef.current;
    const mess = messRef.current;
    if (!bereich || !mess) return;
    const frei = bereich.clientWidth - PLUS_BREITE - LUECKE;
    const kinder = Array.from(mess.children) as HTMLElement[];
    const breiten = kinder.slice(0, n).map((k) => k.getBoundingClientRect().width);
    // Ohne Layout (Breite 0, z. B. jsdom) alles zeigen statt alles zusammenzufassen.
    if (n === 0 || frei <= 0 || breiten.every((w) => w === 0)) return setPassend(n);
    const mehrBreite = kinder[n]?.getBoundingClientRect().width ?? 90;
    const gesamt = breiten.reduce((s, w) => s + w, 0) + LUECKE * (n - 1);
    if (gesamt <= frei) return setPassend(n);
    let summe = 0;
    let k = 0;
    for (let i = 0; i < n; i++) {
      const bis = summe + breiten[i] + (i > 0 ? LUECKE : 0);
      if (bis + LUECKE + mehrBreite > frei) break;
      summe = bis;
      k = i + 1;
    }
    setPassend(k);
  }, [n]);

  useLayoutEffect(() => {
    messen();
    if (typeof ResizeObserver === "undefined" || !bereichRef.current) return;
    const ro = new ResizeObserver(messen);
    ro.observe(bereichRef.current);
    return () => ro.disconnect();
  }, [messen, signatur]);

  const bearbeiteterIndex = e.entwurf?.index ?? null;
  let sichtbar = eintraege.map((_, i) => i).slice(0, passend);
  // Die gerade bearbeitete Pille bleibt sichtbar; zusammengefasst wird von hinten.
  if (bearbeiteterIndex !== null && passend > 0 && passend < n) {
    const pos = eintraege.findIndex((x) => x.index === bearbeiteterIndex);
    if (pos >= passend) sichtbar = [...sichtbar.slice(0, passend - 1), pos];
  }
  const versteckt = n - sichtbar.length;
  const hatAktives = n > 0 || zustand.suche !== "";

  const entwurfsFeld = e.entwurf && e.entwurf.index === null ? e.feld : null;
  const entwurfsTeile: Partial<PillenTeile> = entwurfsFeld
    ? {
        spalte: entwurfsFeld.label,
        operator: e.entwurf?.op ? OPERATOR_LABEL[e.entwurf.op] : undefined,
        wert: typeof e.entwurf?.wert === "string" ? e.entwurf.wert : undefined,
      }
    : {};

  function oeffne(index: number, schritt: 1 | 2 | 3, el: HTMLElement) {
    setAlleOffen(false);
    setAnker(el);
    e.bearbeiten(index, schritt);
  }

  const mehrKlasse = "inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-fill px-2.5 text-sekundaer font-semibold text-label";

  return (
    <div className={`relative flex min-h-[42px] items-center gap-1.5 overflow-hidden rounded-[var(--radius-ap-md)] bg-card px-2 py-[7px] ${className}`}>
      {!ohneSuche && (
        <>
          <div
            className="shrink-0"
            onKeyDown={(ev) => {
              if (ev.key === "Escape" && zustand.suche) zustand.setSuche("");
            }}
          >
            <SearchField value={zustand.suche} onChange={zustand.setSuche} placeholder={suchPlatzhalter} className="w-[220px]" />
          </div>
          <span className="mx-1 h-5 w-[0.5px] shrink-0 bg-sepstrong" aria-hidden="true" />
        </>
      )}

      <div ref={bereichRef} className="flex min-w-0 flex-1 items-center gap-1.5">
        <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
          {sichtbar.map((pos) => {
            const x = eintraege[pos];
            return (
              <FilterPille
                key={`${x.index}-${x.teile.spalte}`}
                teile={x.teile}
                variante="office"
                bearbeitet={bearbeiteterIndex === x.index}
                onSpalte={(el) => oeffne(x.index, 1, el)}
                onOperator={(el) => oeffne(x.index, 2, el)}
                onWert={(el) => oeffne(x.index, 3, el)}
                onEntfernen={() => zustand.entfernen(x.index)}
              />
            );
          })}
          {versteckt > 0 && (
            <button
              type="button"
              data-filter-anker
              aria-haspopup="listbox"
              aria-expanded={alleOffen}
              onClick={(ev) => {
                e.schliessen();
                setAnker(ev.currentTarget);
                setAlleOffen((o) => !o);
              }}
              className={mehrKlasse}
            >
              {passend === 0 ? `${n} Filter` : `+${versteckt} weitere`}
              <ChevronDown size={13} strokeWidth={2} className="text-label2" aria-hidden="true" />
            </button>
          )}
          {entwurfsFeld && <EntwurfsPille teile={entwurfsTeile} />}
        </div>
        <button
          type="button"
          data-filter-anker
          title="Filter hinzufügen"
          aria-label="Filter hinzufügen"
          aria-haspopup="listbox"
          aria-expanded={!!e.entwurf && e.entwurf.index === null}
          onClick={(ev) => {
            if (e.entwurf && e.entwurf.index === null) return e.schliessen();
            setAlleOffen(false);
            setAnker(ev.currentTarget);
            e.starten();
          }}
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-[7px] ${
            e.entwurf && e.entwurf.index === null ? "bg-tintbg text-tint" : "text-label2 hover:bg-fill"
          }`}
        >
          <FunnelPlus size={16} strokeWidth={2} aria-hidden="true" />
        </button>
      </div>

      {/* Unsichtbare Messkopie aller Pillen plus "+N weitere": liefert die Breiten für die Einreihigkeit. */}
      <div ref={messRef} aria-hidden="true" className="pointer-events-none invisible absolute top-0 left-0 flex w-max gap-1.5">
        {eintraege.map((x) => (
          <FilterPille key={x.index} teile={x.teile} variante="office" nurMessen onSpalte={noop} onOperator={noop} onWert={noop} onEntfernen={noop} />
        ))}
        <span className={mehrKlasse}>
          +{n} weitere
          <ChevronDown size={13} aria-hidden="true" />
        </span>
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-2">
        {hatAktives && (
          <button type="button" onClick={zustand.zuruecksetzen} className="text-sekundaer font-medium text-tint-text">
            Zurücksetzen
          </button>
        )}
        {ansichten && (
          <>
            {hatAktives && <span className="h-5 w-[0.5px] bg-sepstrong" aria-hidden="true" />}
            <AnsichtenMenue a={a} zustand={zustand} />
          </>
        )}
      </div>

      {live}

      {e.entwurf && (
        <FilterPopover
          felder={felder}
          e={e}
          anker={anker}
          onSuche={(text) => {
            zustand.setSuche(text);
            e.schliessen();
          }}
        />
      )}
      {alleOffen && (
        <PopoverRahmen anker={anker} breite={320} onSchliessen={() => setAlleOffen(false)} ariaLabel={`Alle Filter (${n})`}>
          <Kopf variante="office">Alle Filter ({n})</Kopf>
          {eintraege.map((x) => (
            <div key={x.index} className="group flex min-h-[30px] items-center gap-2 rounded-[6px] px-2 text-sekundaer text-label hover:bg-fill">
              <button
                type="button"
                onClick={() => {
                  setAlleOffen(false);
                  e.bearbeiten(x.index, x.teile.wert ? 3 : 2);
                }}
                className="min-w-0 flex-1 truncate text-left"
              >
                {x.teile.spalte} {x.teile.operator} <span className="font-semibold">{x.teile.wert}</span>
              </button>
              <button
                type="button"
                onClick={() => zustand.entfernen(x.index)}
                aria-label={`Filter ${[x.teile.spalte, x.teile.operator, x.teile.wert].filter(Boolean).join(" ")} entfernen`}
                className="flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full bg-fill2 text-label2"
              >
                <X size={10} strokeWidth={3} aria-hidden="true" />
              </button>
            </div>
          ))}
          <div className="my-[5px] h-px bg-sep" />
          <button
            type="button"
            onClick={() => {
              setAlleOffen(false);
              e.starten();
            }}
            className="flex min-h-[30px] w-full items-center rounded-[6px] px-2 text-left text-sekundaer text-label hover:bg-tint-solid hover:text-white"
          >
            Filter hinzufügen
          </button>
          <button
            type="button"
            onClick={() => {
              setAlleOffen(false);
              zustand.setBedingungen([]);
            }}
            className="flex min-h-[30px] w-full items-center rounded-[6px] px-2 text-left text-sekundaer text-st-fehlt hover:bg-st-fehlt-bg"
          >
            Alle Filter entfernen
          </button>
        </PopoverRahmen>
      )}
    </div>
  );
}

function noop() {}

function FeldLeiste<T>({ felder, zustand, suchPlatzhalter, ansichten, ohneSuche, className, e, a, eintraege, live }: Gemeinsam<T>) {
  const n = eintraege.length;
  const [ansichtenSeite, setAnsichtenSeite] = useState(false);
  const offen = e.entwurf !== null;
  const schritt = e.entwurf?.schritt ?? 1;
  const schliessen = () => {
    setAnsichtenSeite(false);
    e.schliessen();
  };

  const titel = ansichtenSeite ? "Ansichten" : schritt === 1 || !e.feld ? "Filter hinzufügen" : e.feld.label;
  const linksText = ansichtenSeite ? "‹ Zurück" : schritt === 1 ? "Abbrechen" : schritt === 2 || e.feld?.typ === "janein" ? "‹ Spalte" : "‹ Bedingung";
  const links = (
    <button
      type="button"
      onClick={() => (ansichtenSeite ? setAnsichtenSeite(false) : schritt === 1 ? schliessen() : e.zurueck())}
      className="text-zeile text-tint-text"
    >
      {linksText}
    </button>
  );

  return (
    <div className={`space-y-2 ${className}`}>
      {!ohneSuche && <SearchField groesse="mobil" value={zustand.suche} onChange={zustand.setSuche} placeholder={suchPlatzhalter} />}
      <div className="scrollbar-none flex gap-2 overflow-x-auto">
        <button
          type="button"
          onClick={e.starten}
          aria-haspopup="dialog"
          className="inline-flex h-[34px] shrink-0 items-center gap-1.5 rounded-full bg-tint-solid px-3.5 text-fliess font-semibold text-white"
        >
          <Funnel size={16} strokeWidth={2} aria-hidden="true" />
          Filter
        </button>
        {eintraege.map((x) => (
          <FilterPille
            key={`${x.index}-${x.teile.spalte}`}
            teile={x.teile}
            variante="feld"
            bearbeitet={e.entwurf?.index === x.index}
            onSpalte={() => e.bearbeiten(x.index, 3)}
            onOperator={() => e.bearbeiten(x.index, 3)}
            onWert={() => e.bearbeiten(x.index, 3)}
            onEntfernen={() => zustand.entfernen(x.index)}
          />
        ))}
      </div>
      {(n > 0 || zustand.suche !== "") && (
        <p className="text-sekundaer text-label2">
          {n > 0 && <>{n} Filter aktiv · </>}
          <button type="button" onClick={zustand.zuruecksetzen} className="text-tint-text">
            Zurücksetzen
          </button>
        </p>
      )}
      {live}

      <Sheet offen={offen} onClose={schliessen} titel={titel} links={links}>
        {ansichtenSeite ? (
          <AnsichtenListeFeld a={a} zustand={zustand} onFertig={schliessen} />
        ) : (
          <>
            {schritt === 1 && ansichten && (
              <Liste
                eintraege={[{ id: "ansichten", label: "Ansichten", icon: Bookmark, kachel: "orange", rechts: a.gewaehlte?.name }]}
                aktiv={-1}
                onWaehle={() => setAnsichtenSeite(true)}
                variante="feld"
                listId="ansichten-eintrag"
                ariaLabel="Ansichten"
                navigierbar
              />
            )}
            {schritt === 1 && (
              <SpaltenSchritt
                felder={felder}
                e={e}
                variante="feld"
                onSuche={(text) => {
                  zustand.setSuche(text);
                  schliessen();
                }}
              />
            )}
            {schritt === 2 && <OperatorSchritt e={e} variante="feld" />}
            {schritt === 3 && (
              <>
                <WertSchritt e={e} variante="feld" />
                {e.entwurf?.index != null && (
                  <div className="px-4 pb-6">
                    <button
                      type="button"
                      onClick={() => {
                        zustand.entfernen(e.entwurf!.index!);
                        schliessen();
                      }}
                      className="btn-ap-capsule w-full bg-fill text-st-fehlt"
                    >
                      Filter entfernen
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </Sheet>
    </div>
  );
}
