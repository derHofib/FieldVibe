import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, Plus, X } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { kundenApi, projektAufgabenApi, usersApi, vorgaengeApi } from "../../api/endpoints";
import { SearchableSelect } from "../../components/SearchableSelect";
import type { ChecklistenPunkt, ProjektAufgabe, ProjektAufgabePrioritaet, ProjektSpalte } from "../../types";

const PRIORITAET_OPTIONEN: { wert: ProjektAufgabePrioritaet; label: string }[] = [
  { wert: "niedrig", label: "Niedrig" },
  { wert: "mittel", label: "Mittel" },
  { wert: "hoch", label: "Hoch" },
];

const PRIORITAET_AKTIV_KLASSE: Record<ProjektAufgabePrioritaet, string> = {
  niedrig: "bg-white text-slate-800 shadow-xs dark:bg-stone-900 dark:text-stone-100",
  mittel: "bg-white text-amber-700 shadow-xs dark:bg-stone-900 dark:text-amber-300",
  hoch: "bg-white text-rose-700 shadow-xs dark:bg-stone-900 dark:text-rose-300",
};

/** Neu-Anlage (aufgabe=null) und Bearbeiten teilen sich dieses Panel --
 * unterscheiden sich nur im Titel/Speichern-Verhalten und darin, dass beim
 * Bearbeiten zusaetzlich "Loeschen" erscheint. */
export function ProjektAufgabeDetailPanel({
  projektId,
  spalten,
  aufgabe,
  vorbelegteSpalteId,
  onClose,
}: {
  projektId: string;
  spalten: ProjektSpalte[];
  aufgabe: ProjektAufgabe | null;
  vorbelegteSpalteId?: string;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const istNeu = aufgabe === null;

  const [titel, setTitel] = useState(aufgabe?.titel ?? "");
  const [beschreibung, setBeschreibung] = useState(aufgabe?.beschreibung ?? "");
  const [spalteId, setSpalteId] = useState(aufgabe?.spalte_id ?? vorbelegteSpalteId ?? spalten[0]?.id ?? "");
  const [faelligkeitAm, setFaelligkeitAm] = useState(aufgabe?.faelligkeit_am ?? "");
  const [prioritaet, setPrioritaet] = useState<ProjektAufgabePrioritaet>(aufgabe?.prioritaet ?? "mittel");
  const [zugewiesenAn, setZugewiesenAn] = useState(aufgabe?.zugewiesen_an ?? "");
  const [vorgangId, setVorgangId] = useState(aufgabe?.vorgang_id ?? "");
  const [checkliste, setCheckliste] = useState<ChecklistenPunkt[]>(aufgabe?.checkliste ?? []);
  const [neuerPunkt, setNeuerPunkt] = useState("");

  const { data: users } = useQuery({ queryKey: ["users"], queryFn: () => usersApi.list() });
  const { data: alleVorgaenge } = useQuery({ queryKey: ["vorgaenge-alle"], queryFn: () => vorgaengeApi.list() });
  const { data: verknuepfterVorgang } = useQuery({
    queryKey: ["vorgang", vorgangId],
    queryFn: () => vorgaengeApi.get(vorgangId),
    enabled: !!vorgangId && vorgangId !== aufgabe?.vorgang_id,
  });
  const { data: verknuepfterKunde } = useQuery({
    queryKey: ["kunde", verknuepfterVorgang?.kunde_id],
    queryFn: () => kundenApi.get(verknuepfterVorgang!.kunde_id),
    enabled: !!verknuepfterVorgang?.kunde_id,
  });

  const vorgangAnzeige =
    vorgangId === aufgabe?.vorgang_id
      ? { nummer: aufgabe?.vorgang_vorgangsnummer, kunde: aufgabe?.vorgang_kunde_name }
      : { nummer: verknuepfterVorgang?.vorgangsnummer, kunde: verknuepfterKunde?.name };

  const invalidateBoard = () => {
    queryClient.invalidateQueries({ queryKey: ["projekt-aufgaben", projektId] });
  };

  const speichern = useMutation({
    mutationFn: () => {
      const body = {
        spalte_id: spalteId,
        titel,
        beschreibung: beschreibung || undefined,
        faelligkeit_am: faelligkeitAm || null,
        prioritaet,
        zugewiesen_an: zugewiesenAn || null,
        vorgang_id: vorgangId || null,
        checkliste,
      };
      return istNeu
        ? projektAufgabenApi.create({ projekt_id: projektId, ...body })
        : projektAufgabenApi.update(aufgabe!.id, body);
    },
    onSuccess: () => {
      invalidateBoard();
      onClose();
    },
  });

  const loeschen = useMutation({
    mutationFn: () => projektAufgabenApi.remove(aufgabe!.id),
    onSuccess: () => {
      invalidateBoard();
      onClose();
    },
  });

  const checklistePunktHinzufuegen = () => {
    if (!neuerPunkt.trim()) return;
    setCheckliste((bisher) => [...bisher, { text: neuerPunkt.trim(), erledigt: false }]);
    setNeuerPunkt("");
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 p-6 dark:bg-black/50"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="max-h-full w-full max-w-xl overflow-y-auto rounded-xl border border-slate-200 bg-white dark:border-stone-800 dark:bg-stone-900"
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4 dark:border-stone-800">
          <input
            value={titel}
            onChange={(e) => setTitel(e.target.value)}
            placeholder="Titel der Aufgabe"
            className="w-full border-none p-0 text-base font-bold text-slate-800 outline-none dark:bg-transparent dark:text-stone-100"
          />
          <button
            onClick={onClose}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 dark:text-stone-500 dark:hover:bg-stone-800"
          >
            <X size={16} strokeWidth={2} />
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          <div>
            <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
              Beschreibung
            </label>
            <textarea
              value={beschreibung}
              onChange={(e) => setBeschreibung(e.target.value)}
              rows={3}
              className="w-full resize-none rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
                Fälligkeit
              </label>
              <input
                type="date"
                value={faelligkeitAm}
                onChange={(e) => setFaelligkeitAm(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
                Priorität
              </label>
              <div className="flex gap-0.5 rounded-lg border border-slate-200 bg-slate-100 p-0.5 dark:border-stone-700 dark:bg-stone-800">
                {PRIORITAET_OPTIONEN.map((option) => (
                  <button
                    key={option.wert}
                    onClick={() => setPrioritaet(option.wert)}
                    className={`flex-1 rounded-md px-2 py-1.5 text-xs font-semibold ${
                      prioritaet === option.wert
                        ? PRIORITAET_AKTIV_KLASSE[option.wert]
                        : "text-slate-500 hover:text-slate-700 dark:text-stone-400 dark:hover:text-stone-200"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
              Spalte
            </label>
            <select
              value={spalteId}
              onChange={(e) => setSpalteId(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            >
              {spalten.map((spalte) => (
                <option key={spalte.id} value={spalte.id}>
                  {spalte.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
              Zuständiger
            </label>
            <SearchableSelect
              value={zugewiesenAn}
              onChange={setZugewiesenAn}
              placeholder="Nicht zugewiesen"
              options={(users ?? []).map((u) => ({ value: u.id, label: u.name }))}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
              Verknüpfter Vorgang
            </label>
            {vorgangId ? (
              <div className="flex items-center gap-2.5 rounded-md border border-sky-200 bg-sky-50 px-2.5 py-2 dark:border-sky-500/30 dark:bg-sky-500/10">
                <span className="flex h-6.5 w-6.5 shrink-0 items-center justify-center rounded-md bg-sky-100 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300">
                  <Link2 size={13} strokeWidth={2} />
                </span>
                <button
                  onClick={() => navigate(`/vorgaenge/${vorgangId}`)}
                  className="min-w-0 flex-1 text-left"
                >
                  <p className="truncate text-xs font-bold text-sky-700 dark:text-sky-300">
                    {vorgangAnzeige.nummer ?? "…"}
                  </p>
                  {vorgangAnzeige.kunde && (
                    <p className="truncate text-[11.5px] text-slate-500 dark:text-stone-400">
                      {vorgangAnzeige.kunde}
                    </p>
                  )}
                </button>
                <button
                  onClick={() => setVorgangId("")}
                  title="Verknüpfung entfernen"
                  className="shrink-0 rounded-md p-1 text-slate-400 hover:bg-white/60 dark:text-stone-500"
                >
                  <X size={14} strokeWidth={2} />
                </button>
              </div>
            ) : (
              <SearchableSelect
                value=""
                onChange={setVorgangId}
                placeholder="Vorgang suchen…"
                options={(alleVorgaenge ?? []).map((v) => ({
                  value: v.id,
                  label: `${v.vorgangsnummer} · ${v.titel}`,
                }))}
              />
            )}
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
              Checkliste{checkliste.length > 0 && ` · ${checkliste.filter((p) => p.erledigt).length}/${checkliste.length}`}
            </label>
            <div className="space-y-0.5">
              {checkliste.map((punkt, index) => (
                <div key={index} className="flex items-center gap-2 py-1">
                  <input
                    type="checkbox"
                    checked={punkt.erledigt}
                    onChange={() =>
                      setCheckliste((bisher) =>
                        bisher.map((p, i) => (i === index ? { ...p, erledigt: !p.erledigt } : p)),
                      )
                    }
                    className="h-4 w-4 rounded border-slate-300 text-cyan-600 dark:border-stone-600"
                  />
                  <span
                    className={`flex-1 text-sm ${
                      punkt.erledigt
                        ? "text-slate-400 line-through dark:text-stone-500"
                        : "text-slate-800 dark:text-stone-100"
                    }`}
                  >
                    {punkt.text}
                  </span>
                  <button
                    onClick={() => setCheckliste((bisher) => bisher.filter((_, i) => i !== index))}
                    className="shrink-0 rounded-md p-1 text-slate-300 hover:text-rose-600 dark:text-stone-600 dark:hover:text-rose-400"
                  >
                    <X size={13} strokeWidth={2} />
                  </button>
                </div>
              ))}
              <div className="flex items-center gap-2 py-1">
                <Plus size={14} strokeWidth={2} className="shrink-0 text-slate-400 dark:text-stone-500" />
                <input
                  value={neuerPunkt}
                  onChange={(e) => setNeuerPunkt(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      checklistePunktHinzufuegen();
                    }
                  }}
                  onBlur={checklistePunktHinzufuegen}
                  placeholder="Punkt hinzufügen"
                  className="flex-1 border-none bg-transparent p-0 text-sm text-slate-500 outline-none placeholder:text-slate-400 dark:text-stone-400 dark:placeholder:text-stone-500"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-5 py-4 dark:border-stone-800">
          {istNeu ? (
            <span />
          ) : (
            <button
              onClick={() => {
                if (window.confirm("Aufgabe wirklich löschen?")) loeschen.mutate();
              }}
              disabled={loeschen.isPending}
              className="text-xs font-medium text-slate-400 hover:text-red-600 disabled:opacity-50 dark:text-stone-500 dark:hover:text-red-400"
            >
              Aufgabe löschen
            </button>
          )}
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700 dark:bg-stone-800 dark:text-stone-300"
            >
              Abbrechen
            </button>
            <button
              onClick={() => speichern.mutate()}
              disabled={!titel.trim() || !spalteId || speichern.isPending}
              className="btn-clay rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              Speichern
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
