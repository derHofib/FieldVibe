import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckSquare, KanbanSquare, Link2, ListTree, Plus, X } from "lucide-react";
import { useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { projekteApi, projektAufgabenApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { istUeberfaellig, tageSeit } from "../../config/vorgangDarstellung";
import type { ProjektAufgabe, ProjektAufgabePrioritaet } from "../../types";
import { Karte, SeitenKopf } from "../OfficeUi";
import { ProjektAufgabeDetailPanel } from "./ProjektAufgabeDetailPanel";

const PRIORITAET_BADGE: Record<ProjektAufgabePrioritaet, string> = {
  niedrig: "bg-slate-100 text-slate-800 dark:bg-stone-500/15 dark:text-stone-300",
  mittel: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  hoch: "bg-rose-100 text-rose-800 dark:bg-rose-500/15 dark:text-rose-300",
};

const PRIORITAET_LABEL: Record<ProjektAufgabePrioritaet, string> = {
  niedrig: "Niedrig",
  mittel: "Mittel",
  hoch: "Hoch",
};

/** Asana-artiges Kanban fuer freie Projekte -- im Unterschied zu
 * `VorgaengeKanban` (Spalten = fester Vorgangs-Status) sind Spalten hier je
 * Projekt frei benennbar, und Aufgaben koennen optional auf einen Vorgang
 * verweisen (rein referenziell, siehe ProjektAufgabeDetailPanel). Reihenfolge
 * innerhalb einer Spalte ist bewusst nicht manuell sortierbar -- neue Karten
 * haengen sich unten an, wie im bestehenden VorgaengeKanban auch. */
export function OfficeProjektePage() {
  const queryClient = useQueryClient();
  const [projektId, setProjektId] = useState<string | null>(null);
  const [zeigeNeuesProjekt, setZeigeNeuesProjekt] = useState(false);
  const [neuerProjektName, setNeuerProjektName] = useState("");
  const [neueSpalteName, setNeueSpalteName] = useState<string | null>(null);
  const [panel, setPanel] = useState<{ aufgabe: ProjektAufgabe | null; spalteId?: string } | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: projekte, isLoading: projekteLaden } = useQuery({
    queryKey: ["projekte"],
    queryFn: () => projekteApi.list(),
  });

  const aktivesProjekt = projektId ?? projekte?.[0]?.id ?? null;

  const { data: spalten } = useQuery({
    queryKey: ["projekt-spalten", aktivesProjekt],
    queryFn: () => projekteApi.spalten(aktivesProjekt!),
    enabled: !!aktivesProjekt,
  });

  const { data: aufgaben } = useQuery({
    queryKey: ["projekt-aufgaben", aktivesProjekt],
    queryFn: () => projektAufgabenApi.list({ projekt_id: aktivesProjekt! }),
    enabled: !!aktivesProjekt,
  });

  const projektErstellen = useMutation({
    mutationFn: () => projekteApi.create({ name: neuerProjektName.trim() }),
    onSuccess: (projekt) => {
      setProjektId(projekt.id);
      setZeigeNeuesProjekt(false);
      setNeuerProjektName("");
      queryClient.invalidateQueries({ queryKey: ["projekte"] });
    },
  });

  const spalteErstellen = useMutation({
    mutationFn: (name: string) => projekteApi.createSpalte(aktivesProjekt!, name),
    onSuccess: () => {
      setNeueSpalteName(null);
      queryClient.invalidateQueries({ queryKey: ["projekt-spalten", aktivesProjekt] });
    },
  });

  const spalteVerschieben = useMutation({
    mutationFn: ({ id, spalte_id }: { id: string; spalte_id: string }) =>
      projektAufgabenApi.update(id, { spalte_id }),
    onError: (err) => {
      setFehler(err instanceof ApiError ? err.message : "Aufgabe konnte nicht verschoben werden.");
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["projekt-aufgaben", aktivesProjekt] }),
  });

  const nachSpalte = useMemo(() => {
    const gruppen = new Map<string, ProjektAufgabe[]>();
    // spalte_id ist im Typ nullable (private Aufgaben/Unteraufgaben), aber
    // diese Liste ist immer mit projekt_id gefiltert -- das Backend liefert
    // dort ausschliesslich eigenstaendige Kanban-Karten mit gesetzter Spalte.
    for (const a of aufgaben ?? []) {
      if (!a.spalte_id) continue;
      const liste = gruppen.get(a.spalte_id) ?? [];
      liste.push(a);
      gruppen.set(a.spalte_id, liste);
    }
    return gruppen;
  }, [aufgaben]);

  const handleDrop = (spalteId: string, aufgabeId: string) => {
    const aufgabe = aufgaben?.find((a) => a.id === aufgabeId);
    if (!aufgabe || aufgabe.spalte_id === spalteId) return;
    spalteVerschieben.mutate({ id: aufgabeId, spalte_id: spalteId });
  };

  if (projekteLaden) {
    return <p className="py-10 text-center text-sm text-ind-ink-3">Lädt…</p>;
  }

  return (
    <div>
      <SeitenKopf titel="Projekte">
        {projekte && projekte.length > 0 && (
          <select
            value={aktivesProjekt ?? ""}
            onChange={(e) => setProjektId(e.target.value)}
            className="border border-ind-line bg-transparent px-2.5 py-1.5 text-sm font-medium text-ind-ink"
          >
            {projekte.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}
        <button
          onClick={() => setZeigeNeuesProjekt(true)}
          className="btn-clay flex items-center gap-1.5 rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-2 text-xs font-semibold text-white"
        >
          <Plus size={14} strokeWidth={2.5} />
          Neues Projekt
        </button>
      </SeitenKopf>

      {zeigeNeuesProjekt && (
        <Karte className="mb-4 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[220px] flex-1">
              <label className="mb-1 block text-xs font-medium text-ind-ink-3">Name</label>
              <input
                autoFocus
                value={neuerProjektName}
                onChange={(e) => setNeuerProjektName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && neuerProjektName.trim() && projektErstellen.mutate()}
                placeholder="z. B. Neubau Lagerhalle"
                className="w-full border border-ind-line bg-transparent px-3 py-2 text-sm text-ind-ink"
              />
            </div>
            <button
              onClick={() => projektErstellen.mutate()}
              disabled={!neuerProjektName.trim() || projektErstellen.isPending}
              className="btn-clay rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-xs font-semibold text-white disabled:opacity-40"
            >
              Anlegen
            </button>
            <button
              onClick={() => setZeigeNeuesProjekt(false)}
              className="rounded-lg px-3 py-2 text-xs font-medium text-ind-ink-3"
            >
              Abbrechen
            </button>
          </div>
        </Karte>
      )}

      {fehler && (
        <div className="mb-3 flex items-center justify-between gap-2 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
          <span className="flex items-center gap-1.5">
            <AlertTriangle size={14} strokeWidth={2} /> {fehler}
          </span>
          <button onClick={() => setFehler(null)} className="text-xs underline">
            Ausblenden
          </button>
        </div>
      )}

      {!aktivesProjekt ? (
        <EmptyState icon={KanbanSquare} text="Noch kein Projekt angelegt." />
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {(spalten ?? []).map((spalte) => {
            const karten = nachSpalte.get(spalte.id) ?? [];
            return (
              <div
                key={spalte.id}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const aufgabeId = e.dataTransfer.getData("text/plain");
                  if (aufgabeId) handleDrop(spalte.id, aufgabeId);
                }}
                className="w-72 shrink-0 rounded-lg"
              >
                <div className="mb-2 flex items-center justify-between px-1">
                  <span className="text-xs font-bold text-ind-ink-3">{spalte.name}</span>
                  <span className="rounded-full bg-slate-100 px-1.5 text-[10px] font-bold text-slate-400 dark:bg-stone-800 dark:text-stone-500">
                    {karten.length}
                  </span>
                </div>

                <div className="min-h-[64px] space-y-2">
                  {karten.map((a) => {
                    const ueberfaellig = istUeberfaellig(a.faelligkeit_am);
                    const checklisteGesamt = a.checkliste.length;
                    const checklisteErledigt = a.checkliste.filter((p) => p.erledigt).length;
                    return (
                      <div
                        key={a.id}
                        draggable
                        onDragStart={(e) => {
                          e.dataTransfer.setData("text/plain", a.id);
                          e.dataTransfer.effectAllowed = "move";
                        }}
                        onClick={() => setPanel({ aufgabe: a })}
                        className={`card-interactive w-full cursor-grab rounded-xl border bg-white p-3 text-left dark:bg-stone-900 ${
                          ueberfaellig ? "border-rose-300 dark:border-rose-500/40" : "border-ind-line"
                        }`}
                      >
                        <p className="text-[13px] font-semibold text-ind-ink">{a.titel}</p>
                        {a.vorgang_vorgangsnummer && (
                          <p className="mt-1 flex items-center gap-1 truncate text-[11.5px] text-sky-600 dark:text-sky-300">
                            <Link2 size={11} strokeWidth={2} />
                            {a.vorgang_vorgangsnummer}
                          </p>
                        )}
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${PRIORITAET_BADGE[a.prioritaet]}`}>
                            {PRIORITAET_LABEL[a.prioritaet]}
                          </span>
                          {ueberfaellig && a.faelligkeit_am && (
                            <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-semibold text-rose-800 dark:bg-rose-500/15 dark:text-rose-300">
                              {tageSeit(a.faelligkeit_am)} Tage überfällig
                            </span>
                          )}
                          {checklisteGesamt > 0 && (
                            <span className="flex items-center gap-1 text-[10px] font-medium text-ind-ink-3">
                              <CheckSquare size={11} strokeWidth={2} />
                              {checklisteErledigt}/{checklisteGesamt}
                            </span>
                          )}
                          {!!a.unteraufgaben_gesamt && (
                            <span className="flex items-center gap-1 text-[10px] font-medium text-ind-ink-3">
                              <ListTree size={11} strokeWidth={2} />
                              {a.unteraufgaben_erledigt}/{a.unteraufgaben_gesamt}
                            </span>
                          )}
                        </div>
                        <div className="mt-1.5 flex items-center justify-between gap-2">
                          <span />
                          {a.zugewiesener_name && (
                            <span
                              title={a.zugewiesener_name}
                              className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-violet-100 text-[9px] font-bold text-violet-700 dark:bg-violet-500/15 dark:text-violet-300"
                            >
                              {a.zugewiesener_name
                                .split(" ")
                                .map((t) => t[0])
                                .slice(0, 2)
                                .join("")}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}

                  <button
                    onClick={() => setPanel({ aufgabe: null, spalteId: spalte.id })}
                    className="flex w-full items-center gap-1.5 rounded-lg px-2 py-2 text-xs font-medium text-slate-400 hover:bg-slate-100 dark:text-stone-500 dark:hover:bg-stone-800/60"
                  >
                    <Plus size={13} strokeWidth={2} />
                    Aufgabe hinzufügen
                  </button>
                </div>
              </div>
            );
          })}

          <div className="w-64 shrink-0">
            {neueSpalteName === null ? (
              <button
                onClick={() => setNeueSpalteName("")}
                className="flex w-full items-center gap-1.5 rounded-lg px-2 py-2 text-xs font-medium text-slate-400 hover:bg-slate-100 dark:text-stone-500 dark:hover:bg-stone-800/60"
              >
                <Plus size={13} strokeWidth={2} />
                Spalte hinzufügen
              </button>
            ) : (
              <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white p-1.5 dark:border-stone-800 dark:bg-stone-900">
                <input
                  autoFocus
                  value={neueSpalteName}
                  onChange={(e) => setNeueSpalteName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && neueSpalteName.trim() && spalteErstellen.mutate(neueSpalteName.trim())}
                  placeholder="Name der Spalte"
                  className="w-full border-none bg-transparent px-1 py-1 text-sm outline-none dark:text-stone-100"
                />
                <button
                  onClick={() => neueSpalteName.trim() && spalteErstellen.mutate(neueSpalteName.trim())}
                  className="shrink-0 rounded-md p-1 text-slate-400 hover:text-slate-700 dark:text-stone-500 dark:hover:text-stone-200"
                >
                  <Plus size={14} strokeWidth={2} />
                </button>
                <button
                  onClick={() => setNeueSpalteName(null)}
                  className="shrink-0 rounded-md p-1 text-slate-400 hover:text-rose-600 dark:text-stone-500 dark:hover:text-rose-400"
                >
                  <X size={14} strokeWidth={2} />
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {panel && aktivesProjekt && (
        <ProjektAufgabeDetailPanel
          projektId={aktivesProjekt}
          spalten={spalten ?? []}
          aufgabe={panel.aufgabe}
          vorbelegteSpalteId={panel.spalteId}
          onClose={() => setPanel(null)}
        />
      )}
    </div>
  );
}
