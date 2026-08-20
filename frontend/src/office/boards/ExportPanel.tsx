import { useMutation, useQuery } from "@tanstack/react-query";
import { FileDown, FileText, Image as ImageIcon, Link2, X } from "lucide-react";
import { useState } from "react";

import { kundenApi, maengelApi, vorgaengeApi } from "../../api/endpoints";
import { SearchableSelect } from "../../components/SearchableSelect";
import type { Board, Leistungstyp, VorgangAbrechnungsart } from "../../types";
import type { BoardNode, KlebezettelDaten, TextDaten } from "./types";

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

function notizText(node: BoardNode): string | null {
  if (node.type === "klebezettel") return (node.data as KlebezettelDaten).text;
  if (node.type === "text") return (node.data as TextDaten).text;
  return null;
}

/** Rechtes Panel ueber dem Board: klassischer Datei-Export plus die
 * eigentliche Idee -- einzelne Notizen gezielt als echte Vorgaenge/Maengel
 * anlegen. Bewusst KEIN Ein-Klick-Automatismus: VorgangCreate verlangt
 * kunde_id/abrechnungsart/leistungstyp, MangelCreate einen bestehenden
 * Vorgang -- beides laesst sich nicht aus einer Freitext-Notiz herleiten
 * (siehe Plan). Erfolgreiche Anlage tauscht den Board-Node direkt gegen
 * eine echte VorgangKarteNode. */
export function ExportPanel({
  board,
  nodes,
  onClose,
  onNodeErsetzen,
  onExportPng,
  onExportPdf,
  onExportCsv,
}: {
  board: Board;
  nodes: BoardNode[];
  onClose: () => void;
  onNodeErsetzen: (nodeId: string, vorgangId: string) => void;
  onExportPng: () => void;
  onExportPdf: () => void;
  onExportCsv: () => void;
}) {
  const [format, setFormat] = useState<"png" | "pdf" | "csv">("png");
  const [offenerModus, setOffenerModus] = useState<{ nodeId: string; art: "vorgang" | "mangel" } | null>(null);

  const notizen = nodes.filter((n) => notizText(n) !== null);

  return (
    <div className="absolute inset-0 z-20 flex justify-end bg-slate-900/40" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex h-full w-[420px] flex-col bg-white shadow-2xl dark:bg-stone-900"
      >
        <div className="relative border-b border-slate-100 px-6 py-5 dark:border-stone-800">
          <h2 className="text-base font-bold text-slate-800 dark:text-stone-100">Board exportieren</h2>
          <p className="mt-1 text-xs text-slate-400 dark:text-stone-500">
            „{board.name}“ · {notizen.length} {notizen.length === 1 ? "Notiz" : "Notizen"}
          </p>
          <button
            onClick={onClose}
            className="absolute top-5 right-5 flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 dark:text-stone-500 dark:hover:bg-stone-800"
          >
            <X size={15} strokeWidth={2} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <p className="mb-2.5 text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
            Format
          </p>
          <div className="mb-6 grid grid-cols-3 gap-2.5">
            {(
              [
                { key: "png" as const, icon: ImageIcon, label: "PNG", sub: "Bild, ganzes Board" },
                { key: "pdf" as const, icon: FileText, label: "PDF", sub: "Zum Drucken/Teilen" },
                { key: "csv" as const, icon: FileDown, label: "CSV-Liste", sub: "Notizen als Tabelle" },
              ]
            ).map((f) => (
              <button
                key={f.key}
                onClick={() => setFormat(f.key)}
                className={`rounded-xl p-3.5 text-center ${
                  format === f.key
                    ? "btn-clay bg-linear-to-r from-cyan-500 to-blue-600 text-white"
                    : "border border-slate-200 text-slate-600 dark:border-stone-700 dark:text-stone-300"
                }`}
              >
                <f.icon size={20} strokeWidth={2} className="mx-auto" />
                <div className="mt-2 text-xs font-bold">{f.label}</div>
                <div className={`mt-0.5 text-[10px] ${format === f.key ? "text-white/85" : "text-slate-400 dark:text-stone-500"}`}>
                  {f.sub}
                </div>
              </button>
            ))}
          </div>
          <button
            onClick={() => (format === "png" ? onExportPng() : format === "pdf" ? onExportPdf() : onExportCsv())}
            className="btn-clay mb-6 w-full rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 py-2.5 text-xs font-bold text-white"
          >
            {format.toUpperCase()} herunterladen
          </button>

          <p className="mb-2.5 text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
            In FieldVibe übernehmen
          </p>
          {notizen.length === 0 ? (
            <p className="text-xs text-slate-400 dark:text-stone-500">Keine Klebezettel/Notizen auf diesem Board.</p>
          ) : (
            <div className="space-y-2">
              {notizen.map((n) => (
                <NotizUebernahme
                  key={n.id}
                  node={n}
                  offen={offenerModus?.nodeId === n.id ? offenerModus.art : null}
                  onOeffnen={(art) => setOffenerModus({ nodeId: n.id, art })}
                  onSchliessen={() => setOffenerModus(null)}
                  onErfolg={(vorgangId) => {
                    onNodeErsetzen(n.id, vorgangId);
                    setOffenerModus(null);
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function NotizUebernahme({
  node,
  offen,
  onOeffnen,
  onSchliessen,
  onErfolg,
}: {
  node: BoardNode;
  offen: "vorgang" | "mangel" | null;
  onOeffnen: (art: "vorgang" | "mangel") => void;
  onSchliessen: () => void;
  onErfolg: (vorgangId: string) => void;
}) {
  const text = notizText(node) ?? "";
  return (
    <div className="rounded-xl border border-slate-200 p-3 dark:border-stone-700">
      <p className="line-clamp-2 text-xs font-medium text-slate-700 dark:text-stone-200">{text || "(leer)"}</p>
      {offen === null && (
        <div className="mt-2 flex items-center gap-3">
          <button onClick={() => onOeffnen("vorgang")} className="text-xs font-semibold text-blue-700 dark:text-blue-400">
            → Neuer Vorgang
          </button>
          <button onClick={() => onOeffnen("mangel")} className="text-xs font-semibold text-amber-700 dark:text-amber-400">
            → Mangel melden
          </button>
        </div>
      )}
      {offen === "vorgang" && (
        <NeuerVorgangMiniform titel={text} onAbbrechen={onSchliessen} onErfolg={onErfolg} />
      )}
      {offen === "mangel" && <MangelMeldenMiniform onAbbrechen={onSchliessen} onErfolg={onErfolg} />}
    </div>
  );
}

function NeuerVorgangMiniform({
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
    <div className="mt-2.5 space-y-2 border-t border-slate-100 pt-2.5 dark:border-stone-800">
      <SearchableSelect
        value={kundeId}
        onChange={setKundeId}
        placeholder="Kunde wählen…"
        options={(kunden ?? []).map((k) => ({ value: k.id, label: k.name }))}
      />
      <div className="grid grid-cols-2 gap-2">
        <select
          value={leistungstyp}
          onChange={(e) => setLeistungstyp(e.target.value as Leistungstyp)}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-xs dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
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
          className="rounded-md border border-slate-300 px-2 py-1.5 text-xs dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        >
          {ABRECHNUNGSART_OPTIONEN.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      {erstellen.isError && <p className="text-[11px] text-red-600 dark:text-red-400">Anlegen fehlgeschlagen.</p>}
      <div className="flex items-center gap-2">
        <button
          onClick={() => erstellen.mutate()}
          disabled={!kundeId || erstellen.isPending}
          className="btn-clay flex items-center gap-1 rounded-md bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
        >
          <Link2 size={11} strokeWidth={2.5} /> Vorgang anlegen
        </button>
        <button onClick={onAbbrechen} className="text-xs font-medium text-slate-400 dark:text-stone-500">
          Abbrechen
        </button>
      </div>
    </div>
  );
}

function MangelMeldenMiniform({
  onAbbrechen,
  onErfolg,
}: {
  onAbbrechen: () => void;
  onErfolg: (vorgangId: string) => void;
}) {
  const [vorgangId, setVorgangId] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  // /api/vorgaenge filtert "status" nur auf einen einzelnen Wert (anders als
  // der Feed-Endpoint mit Kommaliste) -- daher ungefiltert laden und die
  // tippbare Auswahl das Eingrenzen per Suchtext machen lassen.
  const { data: vorgaenge } = useQuery({
    queryKey: ["vorgaenge-alle"],
    queryFn: () => vorgaengeApi.list(),
  });

  const melden = useMutation({
    mutationFn: () => maengelApi.create({ vorgang_id: vorgangId, beschreibung }),
    onSuccess: () => onErfolg(vorgangId),
  });

  return (
    <div className="mt-2.5 space-y-2 border-t border-slate-100 pt-2.5 dark:border-stone-800">
      <SearchableSelect
        value={vorgangId}
        onChange={setVorgangId}
        placeholder="Vorgang wählen…"
        options={(vorgaenge ?? []).map((v) => ({ value: v.id, label: `${v.vorgangsnummer} · ${v.titel}` }))}
      />
      <textarea
        value={beschreibung}
        onChange={(e) => setBeschreibung(e.target.value)}
        rows={2}
        placeholder="Beschreibung des Mangels…"
        className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-xs dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      />
      {melden.isError && <p className="text-[11px] text-red-600 dark:text-red-400">Melden fehlgeschlagen.</p>}
      <div className="flex items-center gap-2">
        <button
          onClick={() => melden.mutate()}
          disabled={!vorgangId || !beschreibung.trim() || melden.isPending}
          className="rounded-md bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
        >
          Mangel melden
        </button>
        <button onClick={onAbbrechen} className="text-xs font-medium text-slate-400 dark:text-stone-500">
          Abbrechen
        </button>
      </div>
    </div>
  );
}
