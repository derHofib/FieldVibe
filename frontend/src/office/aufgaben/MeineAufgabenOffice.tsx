import { useQuery } from "@tanstack/react-query";
import { ArrowUpDown, Check, ChevronDown, ListChecks, Plus } from "lucide-react";
import { Fragment, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { projekteApi, projektAufgabenApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { NEU_BUTTON_KLASSE } from "../../components/FormularFeld";
import { PulldownMenu } from "../../components/apple/PulldownMenu";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import { GruppierenMenue } from "../../components/filter/GruppierenMenue";
import { SkeletonList } from "../../components/Skeleton";
import { useAuth } from "../../context/AuthContext";
import { useEscapeSchliesst } from "../../hooks/useEscapeSchliesst";
import { fortschrittText, PrioritaetAnzeige, QuelleAnzeige } from "../../pages/feld/aufgaben/AufgabenBausteine";
import { AufgabePfad } from "../../pages/feld/aufgaben/AufgabePfad";
import {
  faelligText,
  GRUPPIERUNGEN,
  kundeNameVon,
  SORTIERUNGEN,
  type Sortierung,
} from "../../pages/feld/aufgaben/aufgabenLogik";
import { useMeineAufgaben, type MeineAufgabenZustand, type Segment } from "../../pages/feld/aufgaben/useMeineAufgaben";
import type { ProjektAufgabe } from "../../types";
import { heuteIso } from "../../utils/format";
import { Karte, SeitenKopf } from "../OfficeUi";
import { ProjektAufgabeDetailPanel } from "../projekte/ProjektAufgabeDetailPanel";

const SEGMENTE: { wert: Segment; label: string }[] = [
  { wert: "offen", label: "Offen" },
  { wert: "erledigt", label: "Erledigt" },
];

/** Auswahl in der URL (`?auswahl=ID`, `neu` = leeres Panel): Links und Zurück-Taste behalten den Split. */
function useAuswahl() {
  const [params, setParams] = useSearchParams();
  const auswahl = params.get("auswahl");
  const setze = (wert: string | null) =>
    setParams(
      (prev) => {
        const n = new URLSearchParams(prev);
        if (wert) n.set("auswahl", wert);
        else n.delete("auswahl");
        return n;
      },
      { replace: true },
    );
  return [auswahl, setze] as const;
}

/** Panel für eine Aufgabe (oder `null` = neu). Kanban-Aufgaben brauchen die Spalten ihres Projekts zum Bearbeiten. */
export function AufgabePanelHost({
  aufgabe,
  onClose,
  onGanzeSeite,
}: {
  aufgabe: ProjektAufgabe | null;
  onClose: () => void;
  onGanzeSeite?: () => void;
}) {
  const { data: spalten } = useQuery({
    queryKey: ["projekt-spalten", aufgabe?.projekt_id],
    queryFn: () => projekteApi.spalten(aufgabe!.projekt_id!),
    enabled: !!aufgabe?.projekt_id,
  });
  return (
    <ProjektAufgabeDetailPanel
      // Neuer Schlüssel je Aufgabe: das Panel hält seinen Formularzustand in useState.
      key={aufgabe?.id ?? "neu"}
      eingebettet
      projektId={aufgabe?.projekt_id ?? undefined}
      spalten={spalten ?? []}
      aufgabe={aufgabe}
      onClose={onClose}
      onGanzeSeite={onGanzeSeite}
    />
  );
}

function SortierMenue({ wert, onWechsel }: { wert: Sortierung; onWechsel: (s: Sortierung) => void }) {
  const label = SORTIERUNGEN.find((s) => s.wert === wert)?.label ?? "";
  return (
    <PulldownMenu
      ariaLabel="Sortieren"
      ausrichtung="rechts"
      items={SORTIERUNGEN.map((s) => ({ label: s.label, aktiv: s.wert === wert, onSelect: () => onWechsel(s.wert) }))}
      trigger={({ toggeln, triggerRef, offen }) => (
        <button
          ref={triggerRef}
          type="button"
          onClick={toggeln}
          aria-haspopup="menu"
          aria-expanded={offen}
          aria-label={`Sortieren: ${label}`}
          className="flex h-7 items-center gap-1.5 rounded-[7px] px-1.5 text-sekundaer font-medium text-label hover:bg-fill"
        >
          <ArrowUpDown size={15} strokeWidth={2} className="shrink-0" aria-hidden="true" />
          <span className="whitespace-nowrap">{label}</span>
        </button>
      )}
    />
  );
}

function AbhakKreisZeile({ aufgabe, ueberfaellig, onUmschalten }: { aufgabe: ProjektAufgabe; ueberfaellig: boolean; onUmschalten: () => void }) {
  const erledigt = !!aufgabe.erledigt_am;
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={erledigt}
      aria-label={erledigt ? `„${aufgabe.titel}“ wieder öffnen` : `„${aufgabe.titel}“ als erledigt markieren`}
      onClick={(e) => {
        e.stopPropagation();
        onUmschalten();
      }}
      className={`group relative flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full before:absolute before:-inset-2 ${
        erledigt ? "bg-st-erledigt-dot text-white" : ueberfaellig ? "border-[1.5px] border-st-fehlt-dot" : "border-[1.5px] border-label3"
      }`}
    >
      <Check
        size={13}
        strokeWidth={3}
        className={erledigt ? "" : `opacity-0 group-hover:opacity-60 ${ueberfaellig ? "text-st-fehlt" : "text-label2"}`}
        aria-hidden="true"
      />
    </button>
  );
}

function FortschrittZeile({ a }: { a: ProjektAufgabe }) {
  const text = fortschrittText(a);
  return text ? <span className="block text-meta text-label2">{text}</span> : null;
}

const TH = "px-3 py-2 text-left text-meta font-medium tracking-wide text-label2 uppercase";

function AufgabenTabelle({ z, ausgewaehlt, onWaehle, linksAktiv }: { z: MeineAufgabenZustand; ausgewaehlt: string | null; onWaehle: (a: ProjektAufgabe) => void; linksAktiv: boolean }) {
  const navigate = useNavigate();
  const heute = heuteIso();
  // Bei geöffnetem Detail fehlt der Platz: Kunde/Anlage und Priorität stehen dann im Panel.
  const schmal = !!ausgewaehlt;
  const spaltenAnzahl = schmal ? 4 : 6;

  return (
    <Karte className="overflow-hidden p-0">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-fliess">
          <thead>
            <tr className="border-b border-sepstrong">
              <th scope="col" className="w-11 px-3 py-2">
                <span className="sr-only">Erledigt</span>
              </th>
              <th scope="col" className={TH}>Aufgabe</th>
              <th scope="col" className={TH}>Gehört zu</th>
              {!schmal && <th scope="col" className={TH}>Kunde · Anlage</th>}
              <th scope="col" className={TH}>Quelle</th>
              {!schmal && <th scope="col" className={TH}>Priorität</th>}
              <th scope="col" className={`${TH} text-right`}>{z.segment === "erledigt" ? "Erledigt" : "Fällig"}</th>
            </tr>
          </thead>
          <tbody>
            {z.gruppen.map((g) => {
              const zu = z.eingeklappt.includes(g.key);
              return (
                <Fragment key={g.key}>
                  {g.label && (
                    <tr className="border-b border-sep bg-fill">
                      <td colSpan={spaltenAnzahl + 1} className="p-0">
                        <button
                          type="button"
                          aria-expanded={!zu}
                          onClick={() => z.gruppeUmschalten(g.key)}
                          className={`flex w-full items-center gap-1.5 px-3 py-1.5 text-left text-meta font-bold tracking-wide uppercase ${
                            g.warnung ? "text-st-fehlt" : "text-label2"
                          }`}
                        >
                          <ChevronDown size={13} strokeWidth={2} className={`shrink-0 transition-transform ${zu ? "-rotate-90" : ""}`} aria-hidden="true" />
                          {g.label}
                          <span className="font-medium text-label2">{g.aufgaben.length}</span>
                        </button>
                      </td>
                    </tr>
                  )}
                  {!zu &&
                    g.aufgaben.map((a) => {
                      const f = z.segment === "offen" ? faelligText(a.faelligkeit_am, heute) : null;
                      const ueberfaellig = !!f?.ueberfaellig;
                      const gewaehlt = a.id === ausgewaehlt;
                      const kundeAnlage = [kundeNameVon(a), a.anlage_name].filter(Boolean).join(" · ");
                      const erledigtAm = a.erledigt_am ? new Date(a.erledigt_am).toLocaleDateString("de-DE") : null;
                      return (
                        <tr
                          key={a.id}
                          onClick={() => onWaehle(a)}
                          className={`cursor-pointer border-b border-sep last:border-b-0 ${gewaehlt ? "bg-tintbg" : "hover:bg-fill"}`}
                        >
                          <td className="px-3 py-2 align-middle">
                            <AbhakKreisZeile aufgabe={a} ueberfaellig={ueberfaellig} onUmschalten={() => z.umschalten(a)} />
                          </td>
                          <td className="min-w-0 px-3 py-2">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onWaehle(a);
                              }}
                              aria-current={gewaehlt ? "true" : undefined}
                              className={`block max-w-full text-left font-semibold ${a.erledigt_am ? "text-label2 line-through" : "text-label"}`}
                            >
                              {a.titel}
                            </button>
                            <FortschrittZeile a={a} />
                          </td>
                          <td className="px-3 py-2">
                            <AufgabePfad aufgabe={a} linksAktiv={linksAktiv} navigate={navigate} />
                          </td>
                          {!schmal && <td className="px-3 py-2 text-sekundaer text-label2">{kundeAnlage || "–"}</td>}
                          <td className="px-3 py-2 text-sekundaer whitespace-nowrap">
                            <QuelleAnzeige aufgabe={a} />
                          </td>
                          {!schmal && (
                            <td className="px-3 py-2 text-sekundaer whitespace-nowrap">
                              <PrioritaetAnzeige prioritaet={a.prioritaet} />
                            </td>
                          )}
                          <td className={`px-3 py-2 text-right text-sekundaer whitespace-nowrap tabular-nums ${ueberfaellig ? "font-semibold text-st-fehlt" : "text-label2"}`}>
                            {z.segment === "erledigt" ? (erledigtAm ?? "–") : (f?.text ?? "–")}
                          </td>
                        </tr>
                      );
                    })}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </Karte>
  );
}

/** "Meine Aufgaben" im Office: Tabelle über die volle Breite, Gruppieren/Sortieren/Ansichten in der Filterzeile,
 * bei geöffneter Aufgabe Liste links und Panel als Fläche rechts (Muster der Vorgänge). */
export function MeineAufgabenOffice() {
  const navigate = useNavigate();
  const { hatRecht } = useAuth();
  const z = useMeineAufgaben();
  const [auswahl, setAuswahl] = useAuswahl();
  const linksAktiv = hatRecht("projekte", "sehen");

  const neu = auswahl === "neu";
  const ausgewaehlteAufgabe = !neu && auswahl ? (z.sichtbar.find((a) => a.id === auswahl) ?? null) : null;
  // Eine Aufgabe, die durch Filter/Segment aus der Liste fällt, bleibt per ID erreichbar.
  const { data: einzel } = useQuery({
    queryKey: ["projekt-aufgaben", "einzel", auswahl],
    queryFn: () => projektAufgabenApi.get(auswahl!),
    enabled: !!auswahl && !neu && !ausgewaehlteAufgabe,
  });
  const panelAufgabe = neu ? null : (ausgewaehlteAufgabe ?? einzel ?? undefined);
  const panelOffen = neu || (!!auswahl && panelAufgabe !== undefined);

  useEscapeSchliesst(() => setAuswahl(null), panelOffen);

  // N legt eine Aufgabe an -- nicht beim Tippen in Eingabefeldern oder mit Modifikatoren.
  useEffect(() => {
    const beiTaste = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "n" || e.ctrlKey || e.metaKey || e.altKey) return;
      const ziel = e.target as HTMLElement | null;
      if (ziel && (ziel.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(ziel.tagName))) return;
      e.preventDefault();
      setAuswahl("neu");
    };
    document.addEventListener("keydown", beiTaste);
    return () => document.removeEventListener("keydown", beiTaste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const suchtext = z.zustand.sucheVerzoegert.trim();
  const gefiltert = suchtext !== "" || z.zustand.aktiveAnzahl > 0;

  const liste = z.laedt ? (
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
          <button onClick={z.zustand.zuruecksetzen} className="btn-ap mt-1 text-sekundaer">
            Filter zurücksetzen
          </button>
        ) : z.segment === "offen" ? (
          <button onClick={() => setAuswahl("neu")} className={NEU_BUTTON_KLASSE}>
            <Plus size={14} strokeWidth={2.5} aria-hidden="true" />
            Neue Aufgabe
          </button>
        ) : undefined
      }
    />
  ) : (
    <AufgabenTabelle z={z} ausgewaehlt={panelOffen ? auswahl : null} onWaehle={(a) => setAuswahl(a.id)} linksAktiv={linksAktiv} />
  );

  return (
    <div>
      <SeitenKopf
        titel="Meine Aufgaben"
        zusatz={
          z.hatDaten || !z.laedt ? (
            <>
              {z.zahlen.offen} offen
              {z.zahlen.ueberfaellig > 0 && (
                <>
                  {" · "}
                  <span className="text-st-fehlt">{z.zahlen.ueberfaellig} überfällig</span>
                </>
              )}
            </>
          ) : undefined
        }
      >
        <SegmentedControl
          ariaLabel="Aufgaben"
          wert={z.segment}
          onChange={z.setSegment}
          optionen={SEGMENTE.map((s) => ({
            wert: s.wert,
            label: s.wert === "offen" ? `Offen ${z.zahlen.offen}` : `Erledigt${z.anzahlErledigt !== null ? ` ${z.anzahlErledigt}` : ""}`,
          }))}
        />
        <button onClick={() => setAuswahl("neu")} className={NEU_BUTTON_KLASSE} title="Neue Aufgabe (N)">
          <Plus size={14} strokeWidth={2.5} aria-hidden="true" />
          Neue Aufgabe
        </button>
      </SeitenKopf>

      <FilterLeiste
        felder={z.felder}
        zustand={z.zustand}
        suchPlatzhalter="Aufgabe, Projekt, Kunde…"
        ansichten="aufgaben"
        ansichtenZusatz={z.ansichtenZusatz}
        variante="office"
        className="mb-4"
        hinten={
          <span className="flex items-center gap-1">
            <GruppierenMenue
              wert={z.gruppierung}
              optionen={GRUPPIERUNGEN}
              keinWert="keine"
              onWechsel={z.setGruppierung}
              onAlleEinklappen={z.alleEinklappen}
              onAlleAusklappen={z.alleAusklappen}
              alleEingeklappt={z.alleEingeklappt}
            />
            <SortierMenue wert={z.sortierung} onWechsel={z.setSortierung} />
          </span>
        }
      />

      <div className={`grid items-start gap-4 ${panelOffen ? "grid-cols-[minmax(0,1fr)_minmax(420px,520px)]" : "grid-cols-1"}`}>
        <div className="min-w-0">{liste}</div>
        {panelOffen && (
          <Karte className="office-panel sticky top-16 max-h-[calc(100vh-6rem)] overflow-y-auto">
            <section aria-label="Aufgabe">
              <AufgabePanelHost
                aufgabe={panelAufgabe ?? null}
                onClose={() => setAuswahl(null)}
                onGanzeSeite={panelAufgabe ? () => navigate(`/meine-aufgaben/${panelAufgabe.id}`) : undefined}
              />
            </section>
          </Karte>
        )}
      </div>
    </div>
  );
}
