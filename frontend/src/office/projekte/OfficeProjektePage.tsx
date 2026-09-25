import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckSquare, KanbanSquare, Link2, LayoutList, ListTree, Plus, Table2, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import { projekteApi, projektAufgabenApi } from "../../api/endpoints";
import { Monogramm } from "../../components/apple/Monogramm";
import { EmptyState } from "../../components/EmptyState";
import { istUeberfaellig, tageSeit } from "../../config/vorgangDarstellung";
import type { Projekt, ProjektAufgabe, ProjektAufgabePrioritaet } from "../../types";
import { AnsichtUmschalter, Karte, SeitenKopf } from "../OfficeUi";
import { ProjektAufgabeDetailPanel } from "./ProjektAufgabeDetailPanel";
import { ProjektDetailPanel } from "./ProjektDetailPanel";
import { ProjekteTabelle } from "./ProjekteTabelle";
import { ProjektUebersicht } from "./ProjektUebersicht";

const PRIORITAET_BADGE: Record<ProjektAufgabePrioritaet, string> = {
  niedrig: "bg-fill text-label2",
  mittel: "bg-st-arbeit-bg text-st-arbeit",
  hoch: "bg-st-fehlt-bg text-st-fehlt",
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
const ANSICHT_UMSCHALTER = [
  { wert: "tabelle" as const, label: "Tabelle", icon: Table2 },
  { wert: "uebersicht" as const, label: "Übersicht", icon: LayoutList },
  { wert: "kanban" as const, label: "Kanban", icon: KanbanSquare },
];

export function OfficeProjektePage() {
  const queryClient = useQueryClient();
  // "Tabelle" (alle Projekte) ist der neue Standard-Einstieg -- Uebersicht/
  // Kanban bleiben fuer die Detailarbeit an einem einzelnen Projekt.
  const [ansicht, setAnsicht] = useState<"tabelle" | "uebersicht" | "kanban">("tabelle");
  const [projektId, setProjektId] = useState<string | null>(null);
  const [projektPanel, setProjektPanel] = useState<Projekt | null>(null);
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
  // Gleiches Doppel-Submit-Risiko wie bei spalteAnlegen oben -- siehe Kommentar dort.
  const projektAnlegenLaeuft = useRef(false);
  const projektAnlegen = () => {
    if (!neuerProjektName.trim() || projektAnlegenLaeuft.current) return;
    projektAnlegenLaeuft.current = true;
    projektErstellen.mutate(undefined, { onSettled: () => (projektAnlegenLaeuft.current = false) });
  };

  const spalteErstellen = useMutation({
    mutationFn: (name: string) => projekteApi.createSpalte(aktivesProjekt!, name),
    onSuccess: () => {
      setNeueSpalteName(null);
      queryClient.invalidateQueries({ queryKey: ["projekt-spalten", aktivesProjekt] });
    },
  });
  // `spalteErstellen.isPending` allein reicht nicht als Doppel-Submit-Schutz:
  // zwei sehr schnelle Klicks koennen beide feuern, bevor React nach dem
  // ersten mutate()-Aufruf neu gerendert hat und `disabled` tatsaechlich
  // greift. Ref ist synchron, unabhaengig vom Render-Zyklus.
  const spalteAnlegenLaeuft = useRef(false);
  const spalteAnlegen = () => {
    const name = neueSpalteName?.trim();
    if (!name || spalteAnlegenLaeuft.current) return;
    spalteAnlegenLaeuft.current = true;
    spalteErstellen.mutate(name, { onSettled: () => (spalteAnlegenLaeuft.current = false) });
  };

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
    return <p className="py-10 text-center text-sm text-label2">Lädt…</p>;
  }

  return (
    <div>
      <SeitenKopf titel="Projekte">
        {(ansicht === "tabelle" || aktivesProjekt) && (
          <AnsichtUmschalter wert={ansicht} optionen={ANSICHT_UMSCHALTER} onWechsel={setAnsicht} />
        )}
        {ansicht !== "tabelle" && projekte && projekte.length > 0 && (
          <select
            value={aktivesProjekt ?? ""}
            onChange={(e) => setProjektId(e.target.value)}
            className="field-ap"
            style={{ width: "auto", minHeight: 0 }}
          >
            {projekte.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}
        <button onClick={() => setZeigeNeuesProjekt(true)} className="btn-ap-primary">
          <Plus size={14} strokeWidth={2.5} aria-hidden="true" />
          Neues Projekt
        </button>
      </SeitenKopf>

      {zeigeNeuesProjekt && (
        <Karte className="mb-4 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[220px] flex-1">
              <label className="mb-1 block text-xs font-medium text-label2">Name</label>
              <input
                autoFocus
                value={neuerProjektName}
                onChange={(e) => setNeuerProjektName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && projektAnlegen()}
                placeholder="z. B. Neubau Lagerhalle"
                className="field-ap"
              />
            </div>
            <button
              onClick={projektAnlegen}
              disabled={!neuerProjektName.trim() || projektErstellen.isPending}
              className="btn-ap-primary"
            >
              Anlegen
            </button>
            <button onClick={() => setZeigeNeuesProjekt(false)} className="btn-ap">
              Abbrechen
            </button>
          </div>
        </Karte>
      )}

      {fehler && (
        <div className="mb-3 flex items-center justify-between gap-2 rounded-lg bg-st-fehlt-bg px-3 py-2 text-sm text-st-fehlt">
          <span className="flex items-center gap-1.5">
            <AlertTriangle size={14} strokeWidth={2} aria-hidden="true" /> {fehler}
          </span>
          <button onClick={() => setFehler(null)} className="text-xs underline">
            Ausblenden
          </button>
        </div>
      )}

      {ansicht === "tabelle" ? (
        !projekte || projekte.length === 0 ? (
          <EmptyState icon={KanbanSquare} text="Noch kein Projekt angelegt." />
        ) : (
          <ProjekteTabelle projekte={projekte} onZeileKlick={setProjektPanel} />
        )
      ) : !aktivesProjekt ? (
        <EmptyState icon={KanbanSquare} text="Noch kein Projekt angelegt." />
      ) : ansicht === "uebersicht" ? (
        <ProjektUebersicht projektId={aktivesProjekt} />
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
                  <span className="text-xs font-bold text-label2">{spalte.name}</span>
                  <span className="rounded-full bg-fill px-1.5 text-[10px] font-bold text-label3">
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
                        className="card-interactive card-ap w-full cursor-grab p-3"
                        // .card-ap setzt den Rahmen ausserhalb jedes @layer,
                        // siehe gleiche Begruendung in VorgaengeKanban.tsx.
                        style={ueberfaellig ? { borderColor: "var(--st-fehlt-dot)" } : undefined}
                      >
                        <button type="button" onClick={() => setPanel({ aufgabe: a })} className="block w-full text-left">
                          <p className="text-[13px] font-semibold text-label">{a.titel}</p>
                          {a.vorgang_vorgangsnummer && (
                            <p className="mt-1 flex items-center gap-1 truncate text-[11.5px] text-tint">
                              <Link2 size={11} strokeWidth={2} aria-hidden="true" />
                              {a.vorgang_vorgangsnummer}
                            </p>
                          )}
                          <div className="mt-2 flex flex-wrap items-center gap-1.5">
                            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${PRIORITAET_BADGE[a.prioritaet]}`}>
                              {PRIORITAET_LABEL[a.prioritaet]}
                            </span>
                            {ueberfaellig && a.faelligkeit_am && (
                              <span className="rounded-full bg-st-fehlt-bg px-2 py-0.5 text-[10px] font-semibold text-st-fehlt">
                                {tageSeit(a.faelligkeit_am)} Tage überfällig
                              </span>
                            )}
                            {checklisteGesamt > 0 && (
                              <span className="flex items-center gap-1 text-[10px] font-medium text-label2">
                                <CheckSquare size={11} strokeWidth={2} aria-hidden="true" />
                                {checklisteErledigt}/{checklisteGesamt}
                              </span>
                            )}
                            {!!a.unteraufgaben_gesamt && (
                              <span className="flex items-center gap-1 text-[10px] font-medium text-label2">
                                <ListTree size={11} strokeWidth={2} aria-hidden="true" />
                                {a.unteraufgaben_erledigt}/{a.unteraufgaben_gesamt}
                              </span>
                            )}
                          </div>
                          {a.zugewiesener_name && (
                            <div className="mt-1.5 flex items-center justify-end gap-2">
                              <span title={a.zugewiesener_name}>
                                <Monogramm name={a.zugewiesener_name} groesse={20} />
                              </span>
                            </div>
                          )}
                        </button>
                        {/* Tastatur-/Screenreader-Alternative zum Drag&Drop-Spaltenwechsel. */}
                        <label htmlFor={`projekt-spalte-${a.id}`} className="sr-only">
                          Spalte von „{a.titel}“ ändern
                        </label>
                        <select
                          id={`projekt-spalte-${a.id}`}
                          value={a.spalte_id ?? ""}
                          onChange={(e) => handleDrop(e.target.value, a.id)}
                          className="field-ap mt-1.5 h-auto px-1 py-0.5 text-[10px]"
                        >
                          {(spalten ?? []).map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    );
                  })}

                  <button
                    onClick={() => setPanel({ aufgabe: null, spalteId: spalte.id })}
                    className="flex w-full items-center gap-1.5 rounded-lg px-2 py-2 text-xs font-medium text-label3 hover:bg-fill"
                  >
                    <Plus size={13} strokeWidth={2} aria-hidden="true" />
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
                className="flex w-full items-center gap-1.5 rounded-lg px-2 py-2 text-xs font-medium text-label3 hover:bg-fill"
              >
                <Plus size={13} strokeWidth={2} aria-hidden="true" />
                Spalte hinzufügen
              </button>
            ) : (
              <div className="card-ap flex items-center gap-1.5 p-1.5">
                <input
                  autoFocus
                  value={neueSpalteName}
                  disabled={spalteErstellen.isPending}
                  onChange={(e) => setNeueSpalteName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && spalteAnlegen()}
                  placeholder="Name der Spalte"
                  className="w-full border-none bg-transparent px-1 py-1 text-sm text-label outline-none disabled:opacity-50"
                />
                <button
                  onClick={spalteAnlegen}
                  disabled={spalteErstellen.isPending}
                  className="shrink-0 rounded-md p-1 text-label3 hover:text-label disabled:opacity-50"
                >
                  <Plus size={14} strokeWidth={2} aria-hidden="true" />
                </button>
                <button
                  onClick={() => setNeueSpalteName(null)}
                  className="shrink-0 rounded-md p-1 text-label3 hover:text-st-fehlt"
                >
                  <X size={14} strokeWidth={2} aria-hidden="true" />
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

      {projektPanel && (
        <ProjektDetailPanel
          projekt={projektPanel}
          onClose={() => setProjektPanel(null)}
          onKanbanOeffnen={() => {
            setProjektId(projektPanel.id);
            setAnsicht("kanban");
            setProjektPanel(null);
          }}
        />
      )}
    </div>
  );
}
