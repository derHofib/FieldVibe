import { useQuery } from "@tanstack/react-query";
import { Check, ChevronDown, ListChecks } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { projekteApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import { GruppierenMenue } from "../../components/filter/GruppierenMenue";
import { SkeletonList } from "../../components/Skeleton";
import { ProjektAufgabeDetailPanel } from "../../office/projekte/ProjektAufgabeDetailPanel";
import type { ProjektAufgabe } from "../../types";
import { heuteIso } from "../../utils/format";
import { fortschrittText, PrioritaetAnzeige, QuelleAnzeige } from "./aufgaben/AufgabenBausteine";
import { AufgabePfad } from "./aufgaben/AufgabePfad";
import { faelligText, GRUPPIERUNGEN, kundeNameVon } from "./aufgaben/aufgabenLogik";
import { useMeineAufgaben, type Segment } from "./aufgaben/useMeineAufgaben";

const SEGMENTE: { wert: Segment; label: string }[] = [
  { wert: "offen", label: "Offen" },
  { wert: "erledigt", label: "Erledigt" },
];

/** "Meine Aufgaben" in der Feld-App: Karten statt Tabelle (das Office hat eine eigene Seite, siehe
 * office/aufgaben). Aggregiert private Aufgaben (projekt_id=None, siehe app/models/projekt.py) und -- sofern das
 * Kanban-Recht besteht -- alle mir zugewiesenen Projekt-Aufgaben, projektuebergreifend. Neuanlage/Bearbeitung
 * nutzen dasselbe Panel wie das Kanban-Board; Kanban-Aufgaben brauchen dafuer die Spalten ihres Projekts, die
 * erst beim Oeffnen nachgeladen werden. Projekt und Auftrag sind hier nur Text, der Vorgang ein Link: Techniker
 * haben keine Projekt-/Auftragsseiten. */
export function MeineAufgabenPage() {
  const navigate = useNavigate();
  const z = useMeineAufgaben();
  const [panelAufgabe, setPanelAufgabe] = useState<ProjektAufgabe | null | undefined>(undefined);

  const { data: panelSpalten } = useQuery({
    queryKey: ["projekt-spalten", panelAufgabe?.projekt_id],
    queryFn: () => projekteApi.spalten(panelAufgabe!.projekt_id!),
    enabled: !!panelAufgabe?.projekt_id,
  });

  const heute = heuteIso();
  const suchtext = z.zustand.sucheVerzoegert.trim();
  const gefiltert = suchtext !== "" || z.zustand.aktiveAnzahl > 0;
  const gruppiertLabel = GRUPPIERUNGEN.find((g) => g.wert === z.wirksameGruppierung)?.label;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-titel-mobil font-bold text-label">Meine Aufgaben</h1>
        <button type="button" onClick={() => setPanelAufgabe(null)} className="btn-touch text-zeile font-medium text-tint-text">
          + Neue Aufgabe
        </button>
      </div>

      <FilterLeiste
        felder={z.felder}
        zustand={z.zustand}
        suchPlatzhalter="Suchen"
        ansichten="aufgaben"
        ansichtenZusatz={z.ansichtenZusatz}
        variante="feld"
        hinten={
          <GruppierenMenue
            variante="feld"
            wert={z.gruppierung}
            optionen={GRUPPIERUNGEN}
            keinWert="keine"
            onWechsel={z.setGruppierung}
            onAlleEinklappen={z.alleEinklappen}
            onAlleAusklappen={z.alleAusklappen}
            alleEingeklappt={z.alleEingeklappt}
          />
        }
      />

      <SegmentedControl
        ariaLabel="Aufgaben"
        groesse="mobil"
        volleBreite
        wert={z.segment}
        onChange={z.setSegment}
        optionen={SEGMENTE.map((s) => ({
          wert: s.wert,
          label: s.wert === "offen" ? `Offen ${z.zahlen.offen}` : `Erledigt${z.anzahlErledigt !== null ? ` ${z.anzahlErledigt}` : ""}`,
        }))}
      />

      {gruppiertLabel && z.wirksameGruppierung !== "keine" && <p className="text-sekundaer text-label2">Gruppiert nach {gruppiertLabel}</p>}

      {z.laedt ? (
        <SkeletonList count={4} />
      ) : z.fehler && !z.hatDaten ? (
        <FehlerZustand fehler={z.fehler} was="Die Aufgaben" onErneut={z.neuLaden} />
      ) : z.sichtbar.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          text={
            suchtext
              ? `Nichts gefunden für ‚${suchtext}‘`
              : gefiltert
                ? "Keine Treffer für diese Filter"
                : z.segment === "erledigt"
                  ? "Keine erledigten Aufgaben in den letzten 90 Tagen."
                  : "Keine offenen Aufgaben."
          }
          action={
            gefiltert ? (
              <button onClick={z.zustand.zuruecksetzen} className="btn-ap">
                Filter zurücksetzen
              </button>
            ) : undefined
          }
        />
      ) : (
        z.gruppen.map((g) => {
          const zu = z.eingeklappt.includes(g.key);
          return (
            <section key={g.key} className="space-y-1.5" aria-label={g.label || "Aufgaben"}>
              {g.label && (
                <button
                  type="button"
                  aria-expanded={!zu}
                  onClick={() => z.gruppeUmschalten(g.key)}
                  className={`flex w-full items-center gap-1 px-1 pt-2 text-left text-meta font-bold tracking-wide uppercase ${
                    g.warnung ? "text-st-fehlt" : "text-label2"
                  }`}
                >
                  <ChevronDown size={13} strokeWidth={2} className={`shrink-0 transition-transform ${zu ? "-rotate-90" : ""}`} aria-hidden="true" />
                  {g.label} · {g.aufgaben.length}
                </button>
              )}
              {!zu &&
                g.aufgaben.map((a) => {
                  const f = z.segment === "offen" ? faelligText(a.faelligkeit_am, heute) : null;
                  const ueberfaellig = !!f?.ueberfaellig;
                  const kunde = kundeNameVon(a);
                  const fortschritt = fortschrittText(a);
                  const erledigt = !!a.erledigt_am;
                  return (
                    <div
                      key={a.id}
                      onClick={() => setPanelAufgabe(a)}
                      // .card-ap bringt Rand und Schatten unlayered mit; die gewinnen gegen Tailwind-Utilities
                      // (Cascade-Layer-Falle, siehe DESIGN.md). Der rote Rahmen der überfälligen Karte muss
                      // deshalb inline gesetzt werden.
                      className="card-ap card-interactive flex cursor-pointer gap-2.5 p-3"
                      style={ueberfaellig ? { borderColor: "var(--st-fehlt-dot)", borderWidth: 1 } : undefined}
                    >
                      <button
                        type="button"
                        role="checkbox"
                        aria-checked={erledigt}
                        aria-label={erledigt ? `„${a.titel}“ wieder öffnen` : `„${a.titel}“ als erledigt markieren`}
                        onClick={(e) => {
                          e.stopPropagation();
                          z.umschalten(a);
                        }}
                        className={`relative mt-0.5 flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full before:absolute before:-inset-3 ${
                          erledigt
                            ? "bg-st-erledigt-dot text-white"
                            : ueberfaellig
                              ? "border-[1.5px] border-st-fehlt-dot"
                              : "border-[1.5px] border-label3"
                        }`}
                      >
                        {erledigt && <Check size={13} strokeWidth={3} aria-hidden="true" />}
                      </button>
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex items-start justify-between gap-2">
                          <p className={`text-zeile font-semibold ${erledigt ? "text-label2 line-through" : "text-label"}`}>{a.titel}</p>
                          {f && <span className={`shrink-0 text-sekundaer font-semibold ${ueberfaellig ? "text-st-fehlt" : "text-label2"}`}>{f.text}</span>}
                        </div>
                        <AufgabePfad aufgabe={a} linksAktiv={false} navigate={navigate} kurz />
                        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-sekundaer">
                          <QuelleAnzeige aufgabe={a} />
                          <PrioritaetAnzeige prioritaet={a.prioritaet} />
                          {kunde && <span className="rounded-full bg-fill px-2 py-0.5 text-label">{kunde}</span>}
                          {fortschritt && <span className="text-label2">{fortschritt}</span>}
                        </div>
                      </div>
                    </div>
                  );
                })}
            </section>
          );
        })
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
