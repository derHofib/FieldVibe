import { Check } from "lucide-react";
import { useId, useMemo, useState, type InputHTMLAttributes, type ReactNode } from "react";

import { SegmentedControl } from "../apple/SegmentedControl";
import type { KachelFarbe } from "../apple/SymbolKachel";
import { StatusPille } from "../apple/StatusPille";
import { normalisiere } from "./auswerten";
import { Liste, TastaturListe, useListe, zeilenId, type ListenEintrag, type Variante } from "./FilterListe";
import {
  FILTER_TYP_LABEL,
  OPERATOR_LABEL,
  operatorenFuer,
  type FilterFeld,
  type FilterFeldTyp,
  type FilterOperator,
  type FilterOption,
  type FilterWert,
  type RelativerZeitraum,
} from "./typen";
import type { FilterEntwurfZustand } from "./useFilterEntwurf";

const KACHEL_JE_TYP: Record<FilterFeldTyp, KachelFarbe> = {
  text: "blue",
  auswahl: "orange",
  verknuepfung: "indigo",
  person: "green",
  datum: "red",
  zahl: "gray",
  betrag: "green",
  liste: "indigo",
  janein: "gray",
};

/** Eingabefeld je Variante. Office: 13 px über `search-ap-input` (die globale 16-px-Regel für Eingaben gilt dort
 * nicht), Feld: `field-ap` mit 16 px gegen den iOS-Zoom. */
function Eingabe({
  variante,
  suffix,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { variante: Variante; suffix?: string }) {
  if (variante === "feld") {
    return (
      <div className="relative">
        <input {...rest} className={`field-ap ${suffix ? "pr-9" : ""}`} />
        {suffix && <span className="absolute top-1/2 right-3 -translate-y-1/2 text-zeile text-label2">{suffix}</span>}
      </div>
    );
  }
  return (
    <div className="flex h-8 items-center gap-1.5 rounded-[8px] border-[0.5px] border-sep bg-card px-2.5 focus-within:border-tint">
      <input
        {...rest}
        className="search-ap-input min-w-0 flex-1 bg-transparent text-sekundaer text-label outline-none placeholder:text-label3"
      />
      {suffix && <span className="text-sekundaer text-label2">{suffix}</span>}
    </div>
  );
}

function Fuss({
  variante,
  hinweis,
  label,
  onClick,
  deaktiviert,
}: {
  variante: Variante;
  hinweis?: string;
  label: string;
  onClick: () => void;
  deaktiviert?: boolean;
}) {
  if (variante === "feld") {
    return (
      <div className="mt-4 space-y-2">
        {hinweis && <p className="text-sekundaer text-label2">{hinweis}</p>}
        <button type="button" onClick={onClick} disabled={deaktiviert} className="btn-ap-capsule btn-ap-capsule-primary w-full">
          {label}
        </button>
      </div>
    );
  }
  return (
    <>
      <div className="my-[5px] h-px bg-sep" />
      <div className="flex items-center gap-3 px-2 pt-1 pb-0.5">
        {hinweis && <span className="min-w-0 flex-1 text-meta text-label2">{hinweis}</span>}
        <button
          type="button"
          onClick={onClick}
          disabled={deaktiviert}
          className="ml-auto shrink-0 text-sekundaer font-semibold text-tint-text disabled:opacity-45"
        >
          {label}
        </button>
      </div>
    </>
  );
}

function Rahmen({ variante, children }: { variante: Variante; children: ReactNode }) {
  return <div className={variante === "feld" ? "px-4 pt-3 pb-6" : "space-y-1.5"}>{children}</div>;
}

function alsListe(w: FilterWert | undefined): string[] {
  if (Array.isArray(w)) return w;
  return typeof w === "string" && w ? [w] : [];
}

function alsString(w: FilterWert | undefined): string {
  return typeof w === "string" ? w : "";
}

function alsBereich(w: FilterWert | undefined): { von?: string; bis?: string } {
  return w && typeof w === "object" && !Array.isArray(w) && !("relativ" in w) ? w : {};
}

// ---------------------------------------------------------------------------
// Schritt 1: Spalte

export function SpaltenSchritt<T>({
  felder,
  e,
  variante,
  onSuche,
}: {
  felder: FilterFeld<T>[];
  e: FilterEntwurfZustand<T>;
  variante: Variante;
  onSuche: (text: string) => void;
}) {
  const listId = useId();
  const [text, setText] = useState("");
  const treffer = useMemo(() => {
    const q = normalisiere(text);
    return felder.filter((f) => !q || normalisiere(f.label).includes(q));
  }, [felder, text]);
  const stattdessen = text.trim() !== "" && treffer.length === 0;
  const anzahl = stattdessen ? 1 : treffer.length;
  const waehle = (i: number) => (stattdessen ? onSuche(text.trim()) : e.waehleFeld(treffer[i]));
  const l = useListe(anzahl, waehle);

  const eintraege: ListenEintrag[] = stattdessen
    ? [{ id: "__suche", label: `Stattdessen suchen nach ‚${text.trim()}‘` }]
    : treffer.map((f) => ({
        id: f.key,
        label: f.label,
        icon: f.icon,
        kachel: KACHEL_JE_TYP[f.typ],
        rechts: FILTER_TYP_LABEL[f.typ],
        markiert: f.key === e.entwurf?.feldKey,
      }));
  const onWaehle = (id: string) => (id === "__suche" ? onSuche(text.trim()) : e.waehleFeld(felder.find((f) => f.key === id)!));

  if (variante === "feld") {
    return <Liste eintraege={eintraege} aktiv={-1} onWaehle={onWaehle} variante="feld" listId={listId} ariaLabel="Spalten" navigierbar />;
  }
  return (
    <Rahmen variante="office">
      <Eingabe
        variante="office"
        autoFocus
        role="combobox"
        aria-expanded
        aria-controls={listId}
        aria-activedescendant={l.aktiv >= 0 ? zeilenId(listId, l.aktiv) : undefined}
        aria-label="Spalte suchen"
        placeholder="Spalte suchen…"
        value={text}
        onChange={(ev) => setText(ev.target.value)}
        onKeyDown={l.onKeyDown}
      />
      <Liste eintraege={eintraege} aktiv={l.aktiv} onWaehle={onWaehle} variante="office" listId={listId} ariaLabel="Spalten" />
    </Rahmen>
  );
}

// ---------------------------------------------------------------------------
// Schritt 2: Bedingung

export function OperatorSchritt<T>({ e, variante }: { e: FilterEntwurfZustand<T>; variante: Variante }) {
  const feld = e.feld;
  if (!feld) return null;
  // "relativ" gibt es nur als Schnellauswahl im Wert-Schritt, nicht als eigene Bedingung.
  const ops = operatorenFuer(feld).filter((o) => o !== "relativ");
  const eintraege: ListenEintrag[] = ops.map((o) => ({
    id: o,
    label: OPERATOR_LABEL[o],
    markiert: o === e.entwurf?.op,
    trennerDavor: o === "leer" || (o === "nicht_leer" && !ops.includes("leer")) ? ops.indexOf(o) > 0 : false,
  }));
  return (
    <Rahmen variante={variante}>
      <TastaturListe
        eintraege={eintraege}
        onWaehle={(id) => e.waehleOperator(id as FilterOperator)}
        onZurueck={e.zurueck}
        variante={variante}
        ariaLabel="Bedingung"
      />
    </Rahmen>
  );
}

// ---------------------------------------------------------------------------
// Schritt 3: Wert

export function WertSchritt<T>({ e, variante }: { e: FilterEntwurfZustand<T>; variante: Variante }) {
  const feld = e.feld;
  const op = e.entwurf?.op;
  if (!feld || !op) return null;
  const knopf = e.entwurf?.index != null ? "Übernehmen" : variante === "feld" ? "Filter hinzufügen" : "Hinzufügen";
  switch (feld.typ) {
    case "text":
      return <TextWert e={e} feld={feld} variante={variante} knopf={knopf} />;
    case "auswahl":
    case "liste":
    case "verknuepfung":
    case "person":
      return <OptionenWert e={e} feld={feld} variante={variante} knopf={feld.typ === "auswahl" || feld.typ === "liste" ? "Fertig" : knopf} />;
    case "datum":
      return <DatumWert e={e} feld={feld} variante={variante} knopf={knopf} />;
    case "zahl":
    case "betrag":
      return <ZahlWert e={e} feld={feld} variante={variante} knopf={knopf} />;
    case "janein":
      return (
        <Rahmen variante={variante}>
          <TastaturListe
            eintraege={[
              { id: "ja", label: "ja" },
              { id: "nein", label: "nein" },
            ]}
            onWaehle={(id) => e.uebernehmen({ op: "ist", wert: id })}
            onZurueck={e.zurueck}
            variante={variante}
            ariaLabel={feld.label}
          />
        </Rahmen>
      );
  }
}

interface WertProps<T> {
  e: FilterEntwurfZustand<T>;
  feld: FilterFeld<T>;
  variante: Variante;
  knopf: string;
}

function hervorgehoben(label: string, text: string): ReactNode {
  const i = text ? label.toLowerCase().indexOf(text.toLowerCase()) : -1;
  if (i < 0) return label;
  return (
    <>
      {label.slice(0, i)}
      <strong className="font-semibold">{label.slice(i, i + text.length)}</strong>
      {label.slice(i + text.length)}
    </>
  );
}

function TextWert<T>({ e, feld, variante, knopf }: WertProps<T>) {
  const listId = useId();
  const op = e.entwurf!.op!;
  const wert = alsString(e.entwurf!.wert);
  const vorschlaege = useMemo(() => {
    const q = normalisiere(wert);
    return (feld.vorschlaege ?? []).filter((v) => !q || normalisiere(v).includes(q)).slice(0, 6);
  }, [feld.vorschlaege, wert]);
  const eintraege: ListenEintrag[] = [
    ...(variante === "office" ? [{ id: "__eingabe", label: `${feld.label} ${OPERATOR_LABEL[op]} ‚${wert}‘ ↵` }] : []),
    ...vorschlaege.map((v, i) => ({ id: `v:${v}`, label: hervorgehoben(v, wert.trim()), kopfDavor: i === 0 ? "Werte aus der Liste" : undefined })),
  ];
  const waehle = (id: string) => (id === "__eingabe" ? e.uebernehmen() : e.uebernehmen({ wert: id.slice(2) }));
  const l = useListe(eintraege.length, (i) => waehle(eintraege[i].id), variante === "office" && wert ? 0 : -1, () => e.uebernehmen());

  return (
    <Rahmen variante={variante}>
      <Eingabe
        variante={variante}
        autoFocus
        role={variante === "office" ? "combobox" : undefined}
        aria-expanded={variante === "office" ? true : undefined}
        aria-controls={variante === "office" ? listId : undefined}
        aria-activedescendant={variante === "office" && l.aktiv >= 0 ? zeilenId(listId, l.aktiv) : undefined}
        aria-label={`${feld.label} ${OPERATOR_LABEL[op]}`}
        placeholder="Wert eingeben…"
        value={wert}
        onChange={(ev) => e.setWert(ev.target.value)}
        onKeyDown={(ev) => {
          if (ev.key === "Backspace" && wert === "") e.zurueck();
          else l.onKeyDown(ev);
        }}
      />
      {variante === "feld" && <p className="pt-1.5 text-sekundaer text-label2">Groß-/Kleinschreibung egal</p>}
      {eintraege.length > 0 && (
        <Liste
          eintraege={eintraege}
          aktiv={variante === "office" ? l.aktiv : -1}
          onWaehle={waehle}
          variante={variante}
          listId={listId}
          ariaLabel="Vorschläge"
        />
      )}
      {variante === "feld" ? (
        <Fuss variante="feld" label={knopf} onClick={() => e.uebernehmen()} deaktiviert={wert.trim() === ""} />
      ) : (
        <>
          <div className="my-[5px] h-px bg-sep" />
          <p className="px-2 pt-1 pb-0.5 text-meta text-label2">Groß-/Kleinschreibung egal</p>
        </>
      )}
    </Rahmen>
  );
}

function OptionenWert<T>({ e, feld, variante, knopf }: WertProps<T>) {
  const listId = useId();
  const op = e.entwurf!.op!;
  const gewaehlt = alsListe(e.entwurf!.wert);
  const mitSuche = feld.typ === "verknuepfung" || feld.typ === "person";
  const [text, setText] = useState("");
  const optionen = useMemo(() => {
    const q = normalisiere(text);
    return (feld.optionen ?? []).filter((o) => !q || normalisiere(o.label).includes(q)).slice(0, 50);
  }, [feld.optionen, text]);

  function toggle(w: string) {
    if (feld.einzelwert) e.setWert([w]);
    else e.setWert(gewaehlt.includes(w) ? gewaehlt.filter((x) => x !== w) : [...gewaehlt, w]);
  }
  const l = useListe(optionen.length, (i) => toggle(optionen[i].wert), -1, () => e.uebernehmen());

  const segmentOps = (feld.typ === "auswahl" ? ["ist", "ist_nicht"] : feld.typ === "liste" ? ["enthaelt", "enthaelt_nicht"] : []).filter(
    (o) => operatorenFuer(feld).includes(o as FilterOperator),
  ) as FilterOperator[];

  const zeilen = optionen.map((o: FilterOption, i) => {
    const an = gewaehlt.includes(o.wert);
    const label = o.status ? <StatusPille status={o.status} label={o.label} /> : o.label;
    if (variante === "feld") {
      return (
        <button
          key={o.wert}
          type="button"
          onClick={() => toggle(o.wert)}
          aria-pressed={an}
          className="relative flex min-h-11 w-full items-center gap-3 px-4 text-left text-zeile text-label"
        >
          <span className="min-w-0 flex-1">{label}</span>
          {an && <Check size={18} strokeWidth={2.5} className="shrink-0 text-tint" aria-hidden="true" />}
          {i < optionen.length - 1 && <span className="absolute right-0 bottom-0 left-4 h-px bg-sep" aria-hidden="true" />}
        </button>
      );
    }
    const hervor = i === l.aktiv;
    return (
      <button
        key={o.wert}
        type="button"
        role="option"
        id={zeilenId(listId, i)}
        aria-selected={an}
        tabIndex={-1}
        onMouseDown={(ev) => ev.preventDefault()}
        onClick={() => toggle(o.wert)}
        className={`group flex min-h-[30px] w-full items-center gap-2 rounded-[6px] px-2 text-left text-sekundaer ${
          hervor ? "bg-tint-solid text-white" : "text-label hover:bg-tint-solid hover:text-white"
        }`}
      >
        <span
          className={`flex h-4 w-4 shrink-0 items-center justify-center border-[1.5px] ${feld.einzelwert ? "rounded-full" : "rounded-[4px]"} ${
            an ? "border-tint-solid bg-tint-solid text-white" : "border-sepstrong"
          }`}
          aria-hidden="true"
        >
          {an && <Check size={11} strokeWidth={3} />}
        </span>
        <span className="min-w-0 flex-1 truncate">{label}</span>
      </button>
    );
  });

  const hinweis = feld.einzelwert ? undefined : "Mehrere Werte = ‚oder‘";
  const wurzel = {
    tabIndex: mitSuche ? undefined : 0,
    ref: mitSuche ? undefined : (el: HTMLDivElement | null) => el?.focus(),
    "aria-activedescendant": l.aktiv >= 0 ? zeilenId(listId, l.aktiv) : undefined,
    onKeyDown: mitSuche
      ? undefined
      : (ev: React.KeyboardEvent) => {
          if (ev.key === "Backspace") e.zurueck();
          else l.onKeyDown(ev);
        },
  };

  return (
    <Rahmen variante={variante}>
      {segmentOps.length > 1 && (
        <SegmentedControl
          ariaLabel="Bedingung"
          optionen={segmentOps.map((o) => ({ wert: o, label: OPERATOR_LABEL[o] }))}
          wert={op}
          onChange={e.setOp}
          groesse={variante === "feld" ? "mobil" : "desktop"}
          volleBreite
        />
      )}
      {mitSuche && (
        <Eingabe
          variante={variante}
          autoFocus
          role={variante === "office" ? "combobox" : undefined}
          aria-expanded={variante === "office" ? true : undefined}
          aria-controls={variante === "office" ? listId : undefined}
          aria-activedescendant={variante === "office" && l.aktiv >= 0 ? zeilenId(listId, l.aktiv) : undefined}
          aria-label={`${feld.label} suchen`}
          placeholder={`${feld.label} suchen…`}
          value={text}
          onChange={(ev) => setText(ev.target.value)}
          onKeyDown={(ev) => {
            if (ev.key === "Backspace" && text === "") e.zurueck();
            else l.onKeyDown(ev);
          }}
        />
      )}
      {variante === "feld" ? (
        <div className="overflow-hidden rounded-[var(--radius-ap-card)] bg-cell">{zeilen}</div>
      ) : (
        <div
          role="listbox"
          id={listId}
          aria-label={feld.label}
          aria-multiselectable={!feld.einzelwert}
          className="max-h-[260px] overflow-y-auto outline-none"
          {...wurzel}
        >
          {zeilen.length > 0 ? zeilen : <p className="px-2 py-2 text-sekundaer text-label2">Keine Treffer</p>}
        </div>
      )}
      <Fuss variante={variante} hinweis={hinweis} label={knopf} onClick={() => e.uebernehmen()} deaktiviert={gewaehlt.length === 0} />
    </Rahmen>
  );
}

const SCHNELL: { wert: RelativerZeitraum; label: string }[] = [
  { wert: "ueberfaellig", label: "Überfällig (vor heute)" },
  { wert: "heute", label: "Heute" },
  { wert: "woche", label: "Diese Woche" },
  { wert: "naechste_7", label: "Nächste 7 Tage" },
  { wert: "monat", label: "Dieser Monat" },
];

function DatumWert<T>({ e, feld, variante, knopf }: WertProps<T>) {
  const op = e.entwurf!.op!;
  const wert = e.entwurf!.wert;
  const erlaubt = operatorenFuer(feld);
  const segmentOps = (["am", "vor", "nach", "zwischen"] as FilterOperator[]).filter((o) => erlaubt.includes(o));
  const bereich = alsBereich(wert);
  const einzeln = op === "am" || op === "vor" || op === "nach";
  const aktivRelativ = wert && typeof wert === "object" && "relativ" in wert ? wert.relativ : null;

  const eintraege: ListenEintrag[] = [];
  if (erlaubt.includes("relativ")) {
    SCHNELL.forEach((s, i) =>
      eintraege.push({ id: `r:${s.wert}`, label: s.label, markiert: aktivRelativ === s.wert, kopfDavor: i === 0 ? "Schnellauswahl" : undefined }),
    );
  }
  if (erlaubt.includes("leer")) eintraege.push({ id: "leer", label: "ist leer", trennerDavor: true });
  if (erlaubt.includes("nicht_leer")) eintraege.push({ id: "nicht_leer", label: "ist nicht leer", trennerDavor: !erlaubt.includes("leer") });
  const waehle = (id: string) => {
    if (id.startsWith("r:")) e.uebernehmen({ op: "relativ", wert: { relativ: id.slice(2) as RelativerZeitraum } });
    else e.uebernehmen({ op: id as FilterOperator });
  };
  const enter = (ev: React.KeyboardEvent) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      e.uebernehmen();
    } else if (ev.key === "Backspace" && (ev.target as HTMLInputElement).value === "") e.zurueck();
  };
  const listId = useId();

  return (
    <Rahmen variante={variante}>
      {segmentOps.length > 0 && (
        <SegmentedControl
          ariaLabel="Bedingung"
          optionen={segmentOps.map((o) => ({ wert: o, label: OPERATOR_LABEL[o] }))}
          wert={op}
          onChange={e.setOp}
          groesse={variante === "feld" ? "mobil" : "desktop"}
          volleBreite
        />
      )}
      {einzeln && (
        <Eingabe
          variante={variante}
          type="date"
          autoFocus
          aria-label="Datum"
          value={alsString(wert)}
          onChange={(ev) => e.setWert(ev.target.value)}
          onKeyDown={enter}
        />
      )}
      {op === "zwischen" && (
        <div className="grid grid-cols-2 gap-2">
          <Eingabe
            variante={variante}
            type="date"
            autoFocus
            aria-label="Von"
            value={bereich.von ?? ""}
            onChange={(ev) => e.setWert({ ...bereich, von: ev.target.value })}
            onKeyDown={enter}
          />
          <Eingabe
            variante={variante}
            type="date"
            aria-label="Bis"
            value={bereich.bis ?? ""}
            onChange={(ev) => e.setWert({ ...bereich, bis: ev.target.value })}
            onKeyDown={enter}
          />
        </div>
      )}
      {eintraege.length > 0 && (
        <Liste eintraege={eintraege} aktiv={-1} onWaehle={waehle} variante={variante} listId={listId} ariaLabel="Schnellauswahl" />
      )}
      <Fuss
        variante={variante}
        hinweis={erlaubt.includes("relativ") ? "Relative Werte bleiben in Ansichten relativ" : undefined}
        label={knopf}
        onClick={() => e.uebernehmen()}
        deaktiviert={aktivRelativ ? false : einzeln ? alsString(wert) === "" : !bereich.von && !bereich.bis}
      />
    </Rahmen>
  );
}

const VERGLEICH: FilterOperator[] = ["gleich", "ungleich", "gt", "gte", "lt", "lte", "zwischen"];

function ZahlWert<T>({ e, feld, variante, knopf }: WertProps<T>) {
  const op = e.entwurf!.op!;
  const wert = e.entwurf!.wert;
  const segmentOps = VERGLEICH.filter((o) => operatorenFuer(feld).includes(o));
  const suffix = feld.typ === "betrag" ? "€" : undefined;
  const bereich = alsBereich(wert);
  const enter = (ev: React.KeyboardEvent) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      e.uebernehmen();
    } else if (ev.key === "Backspace" && (ev.target as HTMLInputElement).value === "") e.zurueck();
  };
  return (
    <Rahmen variante={variante}>
      <SegmentedControl
        ariaLabel="Bedingung"
        optionen={segmentOps.map((o) => ({ wert: o, label: OPERATOR_LABEL[o] }))}
        wert={op}
        onChange={e.setOp}
        groesse={variante === "feld" ? "mobil" : "desktop"}
        volleBreite
      />
      {op === "zwischen" ? (
        <div className="grid grid-cols-2 gap-2">
          <Eingabe
            variante={variante}
            autoFocus
            inputMode="decimal"
            aria-label="Von"
            placeholder="von"
            suffix={suffix}
            value={bereich.von ?? ""}
            onChange={(ev) => e.setWert({ ...bereich, von: ev.target.value })}
            onKeyDown={enter}
          />
          <Eingabe
            variante={variante}
            inputMode="decimal"
            aria-label="Bis"
            placeholder="bis"
            suffix={suffix}
            value={bereich.bis ?? ""}
            onChange={(ev) => e.setWert({ ...bereich, bis: ev.target.value })}
            onKeyDown={enter}
          />
        </div>
      ) : (
        <Eingabe
          variante={variante}
          autoFocus
          inputMode="decimal"
          aria-label={feld.label}
          placeholder="0,00"
          suffix={suffix}
          value={alsString(wert)}
          onChange={(ev) => e.setWert(ev.target.value)}
          onKeyDown={enter}
        />
      )}
      <Fuss
        variante={variante}
        label={knopf}
        onClick={() => e.uebernehmen()}
        deaktiviert={op === "zwischen" ? !bereich.von && !bereich.bis : alsString(wert).trim() === ""}
      />
    </Rahmen>
  );
}
