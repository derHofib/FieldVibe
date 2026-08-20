import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Link2, Pencil, Trash2, X } from "lucide-react";
import { useState } from "react";

import { kundenApi, maengelApi, vorgaengeApi } from "../../../api/endpoints";
import { SearchableSelect } from "../../../components/SearchableSelect";
import type { KlebezettelDaten, KlebezettelFarbe } from "../../../office/boards/types";
import type { Leistungstyp, VorgangAbrechnungsart } from "../../../types";

const KLEBEZETTEL_FARBEN: KlebezettelFarbe[] = ["gelb", "blau", "gruen", "rosa"];
const FARB_SWATCH: Record<KlebezettelFarbe, string> = {
  gelb: "bg-amber-200",
  blau: "bg-blue-200",
  gruen: "bg-emerald-200",
  rosa: "bg-rose-200",
};
const FARB_LABEL: Record<KlebezettelFarbe, string> = { gelb: "Gelb", blau: "Blau", gruen: "Grün", rosa: "Rosa" };

const LEISTUNGSTYP_OPTIONEN: { value: Leistungstyp; label: string }[] = [
  { value: "installation", label: "Installation" },
  { value: "pruefung", label: "Prüfung" },
  { value: "wartung", label: "Wartung" },
  { value: "stoerung", label: "Störung" },
  { value: "beratung", label: "Beratung" },
  { value: "planung", label: "Planung" },
];

const ABRECHNUNGSART_OPTIONEN: { value: VorgangAbrechnungsart; label: string }[] = [
  { value: "aufwand", label: "Nach Aufwand" },
  { value: "pauschale", label: "Pauschale" },
  { value: "festpreis", label: "Festpreis" },
  { value: "wartungsvertrag", label: "Wartungsvertrag" },
  { value: "gewaehrleistung", label: "Gewährleistung" },
];

/** Grundgeruest fuer beide Sheet-Modi: halbtransparenter Hintergrund +
 * von unten hochfahrendes Panel, matcht den mobilen "Bottom-Sheet"-
 * Baustein, den es sonst so noch nicht gibt -- an anderer Stelle im Handy-
 * Teil wird stattdessen meist auf eine eigene Route navigiert. */
function SheetGeruest({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    // z-50 statt z-40 -- die schwebende Bottom-Nav (components/BottomNav.tsx)
    // liegt selbst auf z-40 und faengt sonst Taps auf den unteren Sheet-
    // Buttons ab, obwohl sie optisch dahinter erscheint.
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-t-2xl bg-white px-5 pt-2.5 pb-6 shadow-2xl dark:bg-stone-900"
        style={{ paddingBottom: "calc(1.5rem + env(safe-area-inset-bottom))" }}
      >
        <div className="mx-auto mb-3.5 h-1 w-9 rounded-full bg-slate-200 dark:bg-stone-700" />
        {children}
      </div>
    </div>
  );
}

/** Neue Notiz per FAB -- bewusst nur Klebezettel (Farbe + Text), keine
 * Werkzeugauswahl wie am Desktop. Platzierung uebernimmt BoardMobilePage. */
export function NeueNotizSheet({
  onAbbrechen,
  onErstellen,
}: {
  onAbbrechen: () => void;
  onErstellen: (daten: KlebezettelDaten) => void;
}) {
  const [text, setText] = useState("");
  const [farbe, setFarbe] = useState<KlebezettelFarbe>("gelb");

  return (
    <SheetGeruest onClose={onAbbrechen}>
      <h2 className="mb-3 text-base font-bold text-slate-800 dark:text-stone-100">Neue Notiz</h2>
      <textarea
        autoFocus
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        placeholder="Was gibt's zu notieren?"
        className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      />
      <div className="mt-3 flex items-center gap-2.5">
        {KLEBEZETTEL_FARBEN.map((f) => (
          <button
            key={f}
            onClick={() => setFarbe(f)}
            aria-label={FARB_LABEL[f]}
            className={`btn-touch h-8 w-8 rounded-full ${FARB_SWATCH[f]} ${
              farbe === f ? "ring-2 ring-offset-2 ring-slate-800 dark:ring-offset-stone-900 dark:ring-stone-100" : ""
            }`}
          />
        ))}
      </div>
      <div className="mt-4 flex gap-3">
        <button
          onClick={() => onErstellen({ text: text.trim(), farbe })}
          disabled={!text.trim()}
          className="btn-clay flex-1 rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
        >
          Auf Board setzen
        </button>
        <button onClick={onAbbrechen} className="px-2 text-sm font-medium text-slate-500 dark:text-stone-400">
          Abbrechen
        </button>
      </div>
    </SheetGeruest>
  );
}

/** Angetippte Notiz -- Vorschau + dieselben Uebernehmen-Aktionen wie im
 * Export-Panel am Desktop (office/boards/ExportPanel.tsx), hier als
 * eigenstaendige Sheet-Ansicht statt Seitenpanel. */
export function NotizAktionSheet({
  daten,
  onAbbrechen,
  onSpeichern,
  onLoeschen,
  onVorgangErstellt,
}: {
  daten: KlebezettelDaten;
  onAbbrechen: () => void;
  onSpeichern: (daten: KlebezettelDaten) => void;
  onLoeschen: () => void;
  onVorgangErstellt: (vorgangId: string) => void;
}) {
  const [modus, setModus] = useState<"ansicht" | "bearbeiten" | "vorgang" | "mangel">("ansicht");
  const [text, setText] = useState(daten.text);
  const [farbe, setFarbe] = useState(daten.farbe);

  if (modus === "bearbeiten") {
    return (
      <SheetGeruest onClose={onAbbrechen}>
        <h2 className="mb-3 text-base font-bold text-slate-800 dark:text-stone-100">Notiz bearbeiten</h2>
        <textarea
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        />
        <div className="mt-3 flex items-center gap-2.5">
          {KLEBEZETTEL_FARBEN.map((f) => (
            <button
              key={f}
              onClick={() => setFarbe(f)}
              aria-label={FARB_LABEL[f]}
              className={`btn-touch h-8 w-8 rounded-full ${FARB_SWATCH[f]} ${
                farbe === f ? "ring-2 ring-offset-2 ring-slate-800 dark:ring-offset-stone-900 dark:ring-stone-100" : ""
              }`}
            />
          ))}
        </div>
        <div className="mt-4 flex gap-3">
          <button
            onClick={() => onSpeichern({ text: text.trim(), farbe })}
            className="btn-clay flex-1 rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 py-2.5 text-sm font-semibold text-white"
          >
            Speichern
          </button>
          <button onClick={onAbbrechen} className="px-2 text-sm font-medium text-slate-500 dark:text-stone-400">
            Abbrechen
          </button>
        </div>
      </SheetGeruest>
    );
  }

  if (modus === "vorgang") {
    return (
      <SheetGeruest onClose={onAbbrechen}>
        <NeuerVorgangForm titel={daten.text} onAbbrechen={() => setModus("ansicht")} onErfolg={onVorgangErstellt} />
      </SheetGeruest>
    );
  }

  if (modus === "mangel") {
    return (
      <SheetGeruest onClose={onAbbrechen}>
        <MangelMeldenForm onAbbrechen={() => setModus("ansicht")} onErfolg={onVorgangErstellt} />
      </SheetGeruest>
    );
  }

  return (
    <SheetGeruest onClose={onAbbrechen}>
      <div className="flex items-start justify-between gap-3">
        <div className={`flex-1 rounded-lg p-3 text-sm font-medium ${FARB_SWATCH[daten.farbe]} bg-opacity-60`}>
          {daten.text || <span className="opacity-60">(leer)</span>}
        </div>
        <button
          onClick={onAbbrechen}
          aria-label="Schließen"
          className="btn-touch flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500 dark:bg-stone-800 dark:text-stone-400"
        >
          <X size={13} strokeWidth={2.5} />
        </button>
      </div>

      <p className="mt-4 mb-1.5 text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
        In FieldVibe übernehmen
      </p>
      <button
        onClick={() => setModus("vorgang")}
        className="btn-touch flex w-full items-center gap-3 border-b border-slate-100 py-3 text-left dark:border-stone-800"
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300">
          <Link2 size={16} strokeWidth={2} />
        </span>
        <span className="flex-1">
          <span className="block text-sm font-bold text-slate-800 dark:text-stone-100">Neuer Vorgang</span>
          <span className="block text-xs text-slate-400 dark:text-stone-500">Kunde, Leistungsart und Abrechnung wählen</span>
        </span>
      </button>
      <button
        onClick={() => setModus("mangel")}
        className="btn-touch flex w-full items-center gap-3 border-b border-slate-100 py-3 text-left dark:border-stone-800"
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
          <AlertTriangle size={16} strokeWidth={2} />
        </span>
        <span className="flex-1">
          <span className="block text-sm font-bold text-slate-800 dark:text-stone-100">Mangel melden</span>
          <span className="block text-xs text-slate-400 dark:text-stone-500">An bestehenden Vorgang hängen</span>
        </span>
      </button>

      <div className="mt-4 flex gap-3">
        <button
          onClick={() => setModus("bearbeiten")}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-slate-100 py-2.5 text-sm font-semibold text-slate-600 dark:bg-stone-800 dark:text-stone-300"
        >
          <Pencil size={14} strokeWidth={2} /> Bearbeiten
        </button>
        <button
          onClick={onLoeschen}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-rose-50 py-2.5 text-sm font-semibold text-rose-600 dark:bg-rose-500/10 dark:text-rose-400"
        >
          <Trash2 size={14} strokeWidth={2} /> Löschen
        </button>
      </div>
    </SheetGeruest>
  );
}

function NeuerVorgangForm({
  titel,
  onAbbrechen,
  onErfolg,
}: {
  titel: string;
  onAbbrechen: () => void;
  onErfolg: (vorgangId: string) => void;
}) {
  const [kundeId, setKundeId] = useState("");
  const [leistungstyp, setLeistungstyp] = useState<Leistungstyp>("stoerung");
  const [abrechnungsart, setAbrechnungsart] = useState<VorgangAbrechnungsart>("aufwand");
  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });

  const erstellen = useMutation({
    mutationFn: () =>
      vorgaengeApi.create({
        kunde_id: kundeId,
        titel: titel.slice(0, 200) || "Aus Board übernommen",
        leistungstyp,
        abrechnungsart,
      }),
    onSuccess: (v) => onErfolg(v.id),
  });

  return (
    <div className="space-y-3">
      <h2 className="text-base font-bold text-slate-800 dark:text-stone-100">Neuer Vorgang</h2>
      <SearchableSelect
        value={kundeId}
        onChange={setKundeId}
        placeholder="Kunde wählen…"
        options={(kunden ?? []).map((k) => ({ value: k.id, label: k.name }))}
      />
      <select
        value={leistungstyp}
        onChange={(e) => setLeistungstyp(e.target.value as Leistungstyp)}
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      >
        {LEISTUNGSTYP_OPTIONEN.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <select
        value={abrechnungsart}
        onChange={(e) => setAbrechnungsart(e.target.value as VorgangAbrechnungsart)}
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      >
        {ABRECHNUNGSART_OPTIONEN.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {erstellen.isError && <p className="text-xs text-red-600 dark:text-red-400">Anlegen fehlgeschlagen.</p>}
      <div className="flex gap-3 pt-1">
        <button
          onClick={() => erstellen.mutate()}
          disabled={!kundeId || erstellen.isPending}
          className="btn-clay flex-1 rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
        >
          Vorgang anlegen
        </button>
        <button onClick={onAbbrechen} className="px-2 text-sm font-medium text-slate-500 dark:text-stone-400">
          Zurück
        </button>
      </div>
    </div>
  );
}

function MangelMeldenForm({
  onAbbrechen,
  onErfolg,
}: {
  onAbbrechen: () => void;
  onErfolg: (vorgangId: string) => void;
}) {
  const [vorgangId, setVorgangId] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const { data: vorgaenge } = useQuery({ queryKey: ["vorgaenge-alle"], queryFn: () => vorgaengeApi.list() });

  const melden = useMutation({
    mutationFn: () => maengelApi.create({ vorgang_id: vorgangId, beschreibung }),
    onSuccess: () => onErfolg(vorgangId),
  });

  return (
    <div className="space-y-3">
      <h2 className="text-base font-bold text-slate-800 dark:text-stone-100">Mangel melden</h2>
      <SearchableSelect
        value={vorgangId}
        onChange={setVorgangId}
        placeholder="Vorgang wählen…"
        options={(vorgaenge ?? []).map((v) => ({ value: v.id, label: `${v.vorgangsnummer} · ${v.titel}` }))}
      />
      <textarea
        value={beschreibung}
        onChange={(e) => setBeschreibung(e.target.value)}
        rows={3}
        placeholder="Beschreibung des Mangels…"
        className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      />
      {melden.isError && <p className="text-xs text-red-600 dark:text-red-400">Melden fehlgeschlagen.</p>}
      <div className="flex gap-3 pt-1">
        <button
          onClick={() => melden.mutate()}
          disabled={!vorgangId || !beschreibung.trim() || melden.isPending}
          className="flex-1 rounded-lg bg-amber-500 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
        >
          Mangel melden
        </button>
        <button onClick={onAbbrechen} className="px-2 text-sm font-medium text-slate-500 dark:text-stone-400">
          Zurück
        </button>
      </div>
    </div>
  );
}
