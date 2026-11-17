import { Bookmark, ChevronDown } from "lucide-react";
import { useState } from "react";

import { PulldownMenu, type PulldownItem } from "../apple/PulldownMenu";
import { Sheet } from "../apple/Sheet";
import { Switch } from "../apple/Switch";
import { Liste, type ListenEintrag } from "./FilterListe";
import type { AnsichtenZustand } from "./useAnsichten";
import type { FilterZustand } from "./useFilterZustand";

/** Dialog "Aktuelle Filter speichern…": Name und Schalter "Als Standard". */
function SpeichernSheet({ a }: { a: AnsichtenZustand }) {
  const [name, setName] = useState("");
  const [alsStandard, setAlsStandard] = useState(false);
  const bereit = name.trim() !== "" && !a.speichernLaeuft;
  const speichern = () => bereit && a.speichern(name.trim(), alsStandard);
  return (
    <Sheet
      offen={a.speichernOffen}
      onClose={() => a.setSpeichernOffen(false)}
      titel="Ansicht speichern"
      links={
        <button type="button" onClick={() => a.setSpeichernOffen(false)} className="text-zeile text-tint-text">
          Abbrechen
        </button>
      }
      rechts={
        <button type="button" onClick={speichern} disabled={!bereit} className="text-zeile font-semibold text-tint-text disabled:opacity-45">
          Speichern
        </button>
      }
    >
      <form
        className="space-y-4 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          speichern();
        }}
      >
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Name der Ansicht"
          aria-label="Name der Ansicht"
          className="field-ap"
        />
        <div className="flex items-center justify-between gap-3">
          <span className="text-zeile text-label">Als Standard</span>
          <Switch checked={alsStandard} onChange={setAlsStandard} ariaLabel="Als Standard" />
        </div>
        <p className="text-sekundaer text-label2">Die Suche wird nicht mitgespeichert.</p>
      </form>
    </Sheet>
  );
}

function menueEintraege(a: AnsichtenZustand, zustand: FilterZustand): PulldownItem[] {
  const hatFilter = zustand.bedingungen.length > 0;
  const items: PulldownItem[] = a.ansichten.map((v) => ({
    label: v.name,
    aktiv: a.aktive?.id === v.id,
    kuerzel: v.istStandard ? "Standard" : undefined,
    onSelect: () => a.anwenden(v),
  }));
  if (items.length > 0) items.push("trenner");
  items.push({ label: "Aktuelle Filter speichern…", disabled: !hatFilter, onSelect: () => a.setSpeichernOffen(true) });
  if (a.gewaehlte && a.weichtAb) {
    const g = a.gewaehlte;
    items.push({ label: `Änderungen in „${g.name}“ übernehmen`, onSelect: () => a.aenderungenUebernehmen(g) });
  }
  if (a.gewaehlte && !a.gewaehlte.istStandard) {
    const g = a.gewaehlte;
    items.push({ label: "Als Standard festlegen", onSelect: () => a.alsStandardSetzen(g) });
  }
  if (a.gewaehlte) {
    const g = a.gewaehlte;
    items.push("trenner", { label: "Ansicht löschen", destruktiv: true, onSelect: () => void a.loeschen(g) });
  }
  return items;
}

/** Office: Menü "Ansichten" in der Filterzeile (Lesezeichen + Name der aktiven Ansicht). */
export function AnsichtenMenue({ a, zustand }: { a: AnsichtenZustand; zustand: FilterZustand }) {
  if (!a.verfuegbar) return null;
  const name = a.gewaehlte?.name ?? "Ansichten";
  return (
    <>
      <PulldownMenu
        ariaLabel="Ansichten"
        items={menueEintraege(a, zustand)}
        trigger={({ toggeln, triggerRef, offen }) => (
          <button
            ref={triggerRef}
            type="button"
            onClick={toggeln}
            aria-haspopup="menu"
            aria-expanded={offen}
            className="flex h-7 max-w-[220px] items-center gap-1.5 rounded-[7px] px-1.5 text-sekundaer font-medium text-label"
          >
            <Bookmark size={15} strokeWidth={2} className="shrink-0" aria-hidden="true" />
            <span className="truncate">{name}</span>
            <ChevronDown size={14} strokeWidth={2} className="shrink-0 text-label2" aria-hidden="true" />
          </button>
        )}
      />
      <SpeichernSheet a={a} />
    </>
  );
}

/** Feld: Ansichten als Liste im Filter-Sheet (Unterseite von Schritt 1). */
export function AnsichtenListeFeld({ a, zustand, onFertig }: { a: AnsichtenZustand; zustand: FilterZustand; onFertig: () => void }) {
  const hatFilter = zustand.bedingungen.length > 0;
  const eintraege: ListenEintrag[] = [
    ...a.ansichten.map((v) => ({ id: `a:${v.id}`, label: v.name, rechts: v.istStandard ? "Standard" : undefined, markiert: a.aktive?.id === v.id })),
    ...(hatFilter ? [{ id: "speichern", label: "Aktuelle Filter speichern…", trennerDavor: a.ansichten.length > 0 }] : []),
    ...(a.gewaehlte && a.weichtAb ? [{ id: "uebernehmen", label: `Änderungen in „${a.gewaehlte.name}“ übernehmen`, trennerDavor: !hatFilter }] : []),
    ...(a.gewaehlte && !a.gewaehlte.istStandard ? [{ id: "standard", label: "Als Standard festlegen" }] : []),
    ...(a.gewaehlte ? [{ id: "loeschen", label: <span className="text-st-fehlt">Ansicht löschen</span>, trennerDavor: true }] : []),
  ];
  function waehle(id: string) {
    const g = a.gewaehlte;
    if (id.startsWith("a:")) {
      const v = a.ansichten.find((x) => x.id === id.slice(2));
      if (v) a.anwenden(v);
      onFertig();
    } else if (id === "speichern") a.setSpeichernOffen(true);
    else if (id === "uebernehmen" && g) a.aenderungenUebernehmen(g);
    else if (id === "standard" && g) a.alsStandardSetzen(g);
    else if (id === "loeschen" && g) void a.loeschen(g);
  }
  return (
    <>
      <Liste eintraege={eintraege} aktiv={-1} onWaehle={waehle} variante="feld" listId="ansichten-liste" ariaLabel="Ansichten" />
      <SpeichernSheet a={a} />
    </>
  );
}
