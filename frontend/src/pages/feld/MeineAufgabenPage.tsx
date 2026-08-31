import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  CheckCircle2,
  KanbanSquare,
  Link2,
  ListChecks,
  MapPin,
  Plus,
  User as UserIcon,
  Users,
} from "lucide-react";
import { useMemo, useState } from "react";

import { projekteApi, projektAufgabenApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { istUeberfaellig, tageSeit } from "../../config/vorgangDarstellung";
import { ProjektAufgabeDetailPanel } from "../../office/projekte/ProjektAufgabeDetailPanel";
import type { ProjektAufgabe, ProjektAufgabePrioritaet } from "../../types";

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

function heuteIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function inTagenIso(n: number): string {
  const datum = new Date();
  datum.setDate(datum.getDate() + n);
  return datum.toISOString().slice(0, 10);
}

type Gruppe = "ueberfaellig" | "heute" | "woche" | "spaeter" | "ohne";

function gruppeVon(a: ProjektAufgabe, heute: string, in7Tagen: string): Gruppe {
  if (!a.faelligkeit_am) return "ohne";
  if (a.faelligkeit_am < heute) return "ueberfaellig";
  if (a.faelligkeit_am === heute) return "heute";
  if (a.faelligkeit_am <= in7Tagen) return "woche";
  return "spaeter";
}

const GRUPPEN_LABEL: Record<Gruppe, string> = {
  ueberfaellig: "Überfällig",
  heute: "Heute",
  woche: "Diese Woche",
  spaeter: "Später",
  ohne: "Ohne Termin",
};

const GRUPPEN_REIHENFOLGE: Gruppe[] = ["ueberfaellig", "heute", "woche", "spaeter", "ohne"];

/** "Meine Aufgaben": aggregiert private Aufgaben (projekt_id=None, siehe
 * app/models/projekt.py) und -- sofern das Kanban-Recht besteht -- alle mir
 * zugewiesenen Projekt-Aufgaben, projektuebergreifend. Bewusst in der
 * Feld-App UND im Office nutzbar (reine Liste, kein Drag&Drop noetig, siehe
 * config/navSeiten.ts). Nutzt fuer Neuanlage/Bearbeitung dasselbe Panel wie
 * das Kanban-Board -- Kanban-Aufgaben brauchen dafuer zusaetzlich die
 * Spalten ihres Projekts, die erst beim Oeffnen des Panels nachgeladen
 * werden (siehe panelSpalten unten). */
export function MeineAufgabenPage() {
  const queryClient = useQueryClient();
  const [neueAufgabe, setNeueAufgabe] = useState("");
  const [panelAufgabe, setPanelAufgabe] = useState<ProjektAufgabe | null | undefined>(undefined);
  const [zeigeErledigt, setZeigeErledigt] = useState(false);

  const { data: aufgaben, isLoading } = useQuery({
    queryKey: ["projekt-aufgaben", "meine"],
    queryFn: () => projektAufgabenApi.list({ mir_zugewiesen: true }),
  });

  const { data: panelSpalten } = useQuery({
    queryKey: ["projekt-spalten", panelAufgabe?.projekt_id],
    queryFn: () => projekteApi.spalten(panelAufgabe!.projekt_id!),
    enabled: !!panelAufgabe?.projekt_id,
  });

  const invalidieren = () => queryClient.invalidateQueries({ queryKey: ["projekt-aufgaben"] });

  const erstellen = useMutation({
    mutationFn: (titel: string) => projektAufgabenApi.create({ titel }),
    onSuccess: () => {
      setNeueAufgabe("");
      invalidieren();
    },
  });

  const umschalten = useMutation({
    mutationFn: ({ id, erledigt }: { id: string; erledigt: boolean }) =>
      projektAufgabenApi.update(id, { erledigt }),
    onSuccess: invalidieren,
  });

  const { offen, erledigt, gruppen } = useMemo(() => {
    const heute = heuteIso();
    const in7Tagen = inTagenIso(7);
    const alle = aufgaben ?? [];
    const offen = alle.filter((a) => !a.erledigt_am);
    const erledigt = alle.filter((a) => a.erledigt_am);
    const gruppen = new Map<Gruppe, ProjektAufgabe[]>();
    for (const a of offen) {
      const g = gruppeVon(a, heute, in7Tagen);
      gruppen.set(g, [...(gruppen.get(g) ?? []), a]);
    }
    return { offen, erledigt, gruppen };
  }, [aufgaben]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">Meine Aufgaben</h1>
        <span className="text-sm font-medium text-slate-400 dark:text-stone-500">{offen.length} offen</span>
      </div>

      <div className="flex items-center gap-2 rounded-lg bg-white p-1 pl-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <input
          value={neueAufgabe}
          onChange={(e) => setNeueAufgabe(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && neueAufgabe.trim()) {
              e.preventDefault();
              erstellen.mutate(neueAufgabe.trim());
            }
          }}
          placeholder="Neue private Aufgabe…"
          className="flex-1 border-none bg-transparent p-1.5 text-sm outline-none placeholder:text-slate-400 dark:text-stone-100 dark:placeholder:text-stone-500"
        />
        <button
          onClick={() => neueAufgabe.trim() && erstellen.mutate(neueAufgabe.trim())}
          disabled={!neueAufgabe.trim() || erstellen.isPending}
          className="btn-touch flex h-10 w-10 shrink-0 items-center justify-center rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 text-white disabled:opacity-50"
        >
          <Plus size={18} strokeWidth={2.5} />
        </button>
      </div>

      {isLoading ? (
        <p className="py-10 text-center text-sm text-slate-400 dark:text-stone-500">Lädt…</p>
      ) : offen.length === 0 ? (
        <EmptyState icon={ListChecks} text="Keine offenen Aufgaben." />
      ) : (
        GRUPPEN_REIHENFOLGE.filter((g) => (gruppen.get(g) ?? []).length > 0).map((g) => (
          <div key={g} className="space-y-1.5">
            <span
              className={`block text-[11px] font-bold tracking-wide uppercase ${
                g === "ueberfaellig"
                  ? "text-rose-600 dark:text-rose-400"
                  : "text-slate-400 dark:text-stone-500"
              }`}
            >
              {GRUPPEN_LABEL[g]}
            </span>
            {gruppen.get(g)!.map((a) => {
              const ueberfaellig = istUeberfaellig(a.faelligkeit_am);
              return (
                <div
                  key={a.id}
                  onClick={() => setPanelAufgabe(a)}
                  className={`card-interactive flex cursor-pointer gap-2.5 rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800 ${
                    ueberfaellig ? "ring-1 ring-rose-300 dark:ring-rose-500/40" : ""
                  }`}
                >
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      umschalten.mutate({ id: a.id, erledigt: true });
                    }}
                    className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 border-slate-300 dark:border-stone-600"
                    title="Als erledigt markieren"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-[13.5px] font-semibold text-slate-800 dark:text-stone-100">{a.titel}</p>
                      {a.faelligkeit_am && (
                        <span
                          className={`shrink-0 text-[11px] font-semibold ${
                            ueberfaellig ? "text-red-600 dark:text-red-400" : "text-slate-400 dark:text-stone-500"
                          }`}
                        >
                          {ueberfaellig ? `vor ${tageSeit(a.faelligkeit_am)} Tagen` : a.faelligkeit_am}
                        </span>
                      )}
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      {a.projekt_id ? (
                        <span className="flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">
                          <KanbanSquare size={11} strokeWidth={2} /> Projekt
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold text-violet-800 dark:bg-violet-500/15 dark:text-violet-300">
                          <UserIcon size={11} strokeWidth={2} /> Privat
                        </span>
                      )}
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${PRIORITAET_BADGE[a.prioritaet]}`}>
                        {PRIORITAET_LABEL[a.prioritaet]}
                      </span>
                      {a.vorgang_id && (
                        <Link2 size={13} strokeWidth={2} className="text-sky-500 dark:text-sky-400" />
                      )}
                      {a.kunde_id && <Users size={13} strokeWidth={2} className="text-emerald-500 dark:text-emerald-400" />}
                      {a.anlage_id && <Building2 size={13} strokeWidth={2} className="text-amber-500 dark:text-amber-400" />}
                      {a.standort_id && <MapPin size={13} strokeWidth={2} className="text-rose-500 dark:text-rose-400" />}
                      {!!a.unteraufgaben_gesamt && (
                        <span className="text-[10px] font-medium text-slate-400 dark:text-stone-500">
                          {a.unteraufgaben_erledigt}/{a.unteraufgaben_gesamt} Unteraufgaben
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ))
      )}

      {erledigt.length > 0 && (
        <div>
          <button
            onClick={() => setZeigeErledigt((v) => !v)}
            className="flex items-center gap-1.5 py-1 text-xs font-medium text-slate-400 dark:text-stone-500"
          >
            <CheckCircle2 size={14} strokeWidth={2} className="text-green-600 dark:text-green-400" />
            {erledigt.length} erledigt
          </button>
          {zeigeErledigt && (
            <div className="mt-1.5 space-y-1.5">
              {erledigt.map((a) => (
                <div
                  key={a.id}
                  onClick={() => setPanelAufgabe(a)}
                  className="card-interactive flex cursor-pointer items-center gap-2.5 rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
                >
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      umschalten.mutate({ id: a.id, erledigt: false });
                    }}
                    className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-green-600 text-white"
                  >
                    <CheckCircle2 size={13} strokeWidth={2.5} />
                  </button>
                  <p className="flex-1 text-[13.5px] text-slate-400 line-through dark:text-stone-500">{a.titel}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {panelAufgabe !== undefined && (
        <ProjektAufgabeDetailPanel
          projektId={panelAufgabe?.projekt_id ?? undefined}
          spalten={panelSpalten ?? []}
          aufgabe={panelAufgabe}
          onClose={() => setPanelAufgabe(undefined)}
        />
      )}
    </div>
  );
}
