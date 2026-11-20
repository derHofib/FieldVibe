import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { datumZuIso } from "../../utils/format";
import { KanbanSquare, Plus, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { useNavigate } from "react-router-dom";

import { materialBedarfeApi, projekteApi, termineApi, usersApi, zeiterfassungApi } from "../../api/endpoints";
import { AktionsMenue } from "../../components/AktionsMenue";
import { useAuth } from "../../context/AuthContext";
import { ZeiteintragSheet } from "../../components/ZeiteintragSheet";
import { ZeitSummenBlock } from "../../components/ZeitSummenBlock";
import { SeitenPanel } from "../../components/apple/SeitenPanel";
import { ClaudeMarke } from "../../components/formModul/ClaudeMarke";
import { StatusPille } from "../../components/apple/StatusPille";
import { Abschnitt, ABSCHNITT_AKTION } from "../../pages/feld/vorgang/Abschnitt";
import { formatDatum } from "../../utils/format";
import type { Projekt, Zeiterfassung } from "../../types";
import { formatSekundenAlsHHMM } from "../../utils/duration";
import { BUCHUNGSSTATUS_LABEL, buchungsstatusZuToken } from "../../utils/zeiterfassung";
import { VorOrtKontakteAbschnitt } from "../../pages/feld/vorOrt/VorOrtKontakteAbschnitt";
import { AuftraegeUndVorgaenge, ProjektKennzahlen, useProjektInhalt } from "./AuftraegeUndVorgaenge";
import { ProjektAuftraggeberAbschnitt, ProjektRechnungAnAbschnitt } from "./ProjektAuftraggeberAbschnitt";
import { ZeitplanTab } from "./zeitplan/ZeitplanTab";

// Fuer den Termine-Wochenkalender -- gleiche Rechenlogik wie in
// VorgangDetailPage.tsx (dort Kommentar zu WOCHENTAGE) und
// office/dispo/OfficeDispoPage.tsx, hier ebenfalls lokal kopiert statt
// importiert (kein geteiltes Modul, siehe dortige Begruendung).
const WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

function startOfWoche(d: Date): Date {
  const date = new Date(d);
  const tag = date.getDay();
  const diffZuMontag = tag === 0 ? -6 : 1 - tag;
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() + diffZuMontag);
  return date;
}
function addTage(d: Date, n: number): Date {
  const date = new Date(d);
  date.setDate(date.getDate() + n);
  return date;
}
function tagesSchluessel(d: Date): string {
  return datumZuIso(d);
}

const TABS: { key: "uebersicht" | "zeit" | "termine" | "positionen" | "zeitplan"; label: string }[] = [
  { key: "uebersicht", label: "Übersicht" },
  { key: "zeit", label: "Zeit" },
  { key: "termine", label: "Termine" },
  { key: "positionen", label: "Positionen" },
  { key: "zeitplan", label: "Zeitplan" },
];

/** Detailinhalt fuer das rechte SeitenPanel -- echte Tabs (role="tablist",
 * gleiches Muster wie VorgangDetailPage.tsx im layout="dicht"-Modus,
 * siehe dortiger Kommentar zu ANCHOR_ABSCHNITTE): Übersicht (Stammdaten +
 * Kennzahlen + Auftraege-/Vorgaenge-Listen), Zeit (Tabelle, projektweit),
 * Termine (Wochenkalender, projektweit), Positionen (Material-Bedarfe-
 * Tabelle, projektweit). "Kanban öffnen" wechselt in die bestehende
 * Aufgaben-Tafel (OfficeProjektePage.tsx), die fuer EIN Projekt gebaut ist
 * und hier bewusst nicht dupliziert wird. */
export function ProjektDetailPanel({
  projekt,
  startTab,
  onClose,
  onKanbanOeffnen,
}: {
  projekt: Projekt;
  startTab?: "zeitplan";
  onClose: () => void;
  onKanbanOeffnen: () => void;
}) {
  const uid = useId();
  const { hatRecht } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [bearbeiten, setBearbeiten] = useState(false);
  const [name, setName] = useState(projekt.name);
  const [beschreibung, setBeschreibung] = useState(projekt.beschreibung ?? "");
  const [archiviertForm, setArchiviertForm] = useState(projekt.archiviert);
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>(startTab ?? "uebersicht");
  const [terminWocheOffset, setTerminWocheOffset] = useState(0);
  const [sheetEintrag, setSheetEintrag] = useState<Zeiterfassung | null>(null);

  const { data: aktuell } = useQuery({
    queryKey: ["projekte", projekt.id],
    queryFn: () => projekteApi.get(projekt.id),
    initialData: projekt,
  });

  const { auftraege, vorgaenge, laedt: inhaltLaedt } = useProjektInhalt(projekt.id);

  const { data: users } = useQuery({ queryKey: ["users", "auswahl"], queryFn: usersApi.auswahl, enabled: tab === "zeit" });

  const { data: zeiterfassungListe } = useQuery({
    queryKey: ["zeiterfassung", "projekt", projekt.id],
    queryFn: () => zeiterfassungApi.listFuerZeitraum({ projekt_id: projekt.id }),
    enabled: tab === "zeit",
  });

  const { data: termine } = useQuery({
    queryKey: ["termine", "projekt", projekt.id],
    queryFn: () => termineApi.list({ projekt_id: projekt.id }),
    enabled: tab === "termine",
  });

  const { data: materialBedarfe } = useQuery({
    queryKey: ["material-bedarfe", "projekt", projekt.id],
    queryFn: () => materialBedarfeApi.list({ projekt_id: projekt.id }),
    enabled: tab === "positionen",
  });

  const aktualisieren = useMutation({
    mutationFn: (body: Parameters<typeof projekteApi.update>[1]) => projekteApi.update(projekt.id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projekte"] });
      queryClient.invalidateQueries({ queryKey: ["projekte", projekt.id] });
      setBearbeiten(false);
    },
  });

  const bedarfEntfernenMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: (id: string) => materialBedarfeApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["material-bedarfe", "projekt", projekt.id] }),
  });

  const aktiv = aktuell ?? projekt;
  // Ohne eigenen Auftraggeber am Projekt: nur anzeigen, wenn alle Aufträge denselben haben.
  const kundenNamen = new Set((auftraege ?? []).map((a) => a.kunde_name).filter(Boolean));
  const kundeName = aktiv.kunde_name ?? (kundenNamen.size === 1 ? [...kundenNamen][0] : null);

  const zeitEintraegeAbgeschlossen = (zeiterfassungListe ?? [])
    .filter((e) => e.ende_at)
    .sort((a, b) => new Date(b.start_at).getTime() - new Date(a.start_at).getTime());

  return (
    <SeitenPanel
      offen
      titel={aktuell?.name ?? projekt.name}
      onClose={onClose}
      minBreite={tab === "zeitplan" ? 1100 : undefined}
      aktionen={
        <button onClick={onKanbanOeffnen} className="btn-ap flex items-center gap-1.5 text-sekundaer">
          <KanbanSquare size={14} strokeWidth={2} aria-hidden="true" />
          Kanban öffnen
        </button>
      }
    >
      <div className="space-y-2 px-4 pt-4">
        <div className="flex items-center gap-2">
          <span className="text-meta font-semibold tracking-wide text-label2 uppercase">Projekt</span>
          <StatusPille status={aktiv.archiviert ? "geplant" : "arbeit"} label={aktiv.archiviert ? "Archiviert" : "Aktiv"} />
          {aktiv.erstellt_via === "ki" && <ClaudeMarke label="per KI" klein />}
        </div>
        <h1 className="font-heading text-titel-mobil font-bold text-label">{aktiv.name}</h1>
        {kundeName && <p className="text-fliess text-label2">{kundeName}</p>}
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          <button
            type="button"
            onClick={() => navigate(`/auftraege?neu=1&projekt_id=${projekt.id}`)}
            className="btn-touch btn-ap-primary inline-flex items-center gap-1.5 px-3 text-sekundaer"
          >
            <Plus size={14} strokeWidth={2.5} aria-hidden="true" /> Auftrag
          </button>
          <button
            type="button"
            onClick={() => navigate(`/neu?projekt_id=${projekt.id}`)}
            className="btn-touch btn-ap inline-flex items-center gap-1.5 px-3 text-sekundaer"
          >
            <Plus size={14} strokeWidth={2.5} aria-hidden="true" /> Vorgang
          </button>
        </div>
      </div>

      <div
        role="tablist"
        aria-label="Projekt-Abschnitte"
        className="mt-3 mb-3 flex gap-1 overflow-x-auto border-b border-sep px-4 pt-3 pb-2 text-fliess"
      >
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            id={`projekt-tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`projekt-tabpanel-${t.key}`}
            onClick={() => setTab(t.key)}
            className={`shrink-0 rounded-[7px] px-2.5 py-1 font-medium whitespace-nowrap ${
              tab === t.key ? "bg-fill text-label" : "text-label2 hover:text-label"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "uebersicht" && (
        <div
          id="projekt-tabpanel-uebersicht"
          role="tabpanel"
          aria-labelledby="projekt-tab-uebersicht"
          className="space-y-4 p-4 pt-0"
        >
          <ProjektKennzahlen projekt={aktiv} auftraege={auftraege} vorgaenge={vorgaenge} />

          <ProjektAuftraggeberAbschnitt projekt={aktiv} />
          <ProjektRechnungAnAbschnitt projekt={aktiv} />
          <VorOrtKontakteAbschnitt
            ziel="projekt"
            zielId={projekt.id}
            kundeId={aktiv.kunde_id ?? null}
            standortId={aktiv.standort_id ?? null}
            darfBearbeiten={hatRecht("projekte", "bearbeiten")}
            darfKorrigieren={hatRecht("vorgaenge", "bearbeiten")}
            layout="office"
          />

          <AuftraegeUndVorgaenge
            projektId={projekt.id}
            auftraege={auftraege}
            vorgaenge={vorgaenge}
            laedt={inhaltLaedt}
            navigate={navigate}
          />

          <Abschnitt
            titel="Details"
            aktion={
              !bearbeiten ? (
                <button
                  type="button"
                  onClick={() => {
                    setName(aktiv.name);
                    setBeschreibung(aktiv.beschreibung ?? "");
                    setArchiviertForm(aktiv.archiviert);
                    setBearbeiten(true);
                  }}
                  className={ABSCHNITT_AKTION}
                >
                  Bearbeiten
                </button>
              ) : undefined
            }
          >
            {bearbeiten ? (
              <div className="space-y-3">
                <div>
                  <label htmlFor={`${uid}-0`} className="mb-1.5 block text-meta font-bold text-label3">Name</label>
                  <input id={`${uid}-0`} value={name} onChange={(e) => setName(e.target.value)} className="field-ap" />
                </div>
                <div>
                  <label htmlFor={`${uid}-1`} className="mb-1.5 block text-meta font-bold text-label3">Beschreibung</label>
                  <textarea id={`${uid}-1`} value={beschreibung} onChange={(e) => setBeschreibung(e.target.value)} rows={3} className="field-ap" />
                </div>
                <label className="flex items-center gap-2 text-fliess text-label">
                  <input
                    type="checkbox"
                    checked={archiviertForm}
                    onChange={(e) => setArchiviertForm(e.target.checked)}
                    className="h-4 w-4"
                  />
                  Archiviert
                </label>
                <div className="flex justify-end gap-2">
                  <button type="button" onClick={() => setBearbeiten(false)} className="btn-touch btn-ap px-3 text-sekundaer">
                    Abbrechen
                  </button>
                  <button
                    type="button"
                    disabled={!name.trim() || aktualisieren.isPending}
                    onClick={() => aktualisieren.mutate({ name: name.trim(), beschreibung: beschreibung.trim(), archiviert: archiviertForm })}
                    className="btn-touch btn-ap-primary px-3 text-sekundaer"
                  >
                    Speichern
                  </button>
                </div>
              </div>
            ) : (
              <dl className="space-y-1.5 text-fliess">
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="text-label2">Status</dt>
                  <dd className="font-medium text-label">{aktiv.archiviert ? "Archiviert" : "Aktiv"}</dd>
                </div>
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="text-label2">Erstellt am</dt>
                  <dd className="font-medium text-label">{formatDatum(aktiv.created_at)}</dd>
                </div>
                {aktiv.beschreibung && <p className="whitespace-pre-line pt-1 text-label">{aktiv.beschreibung}</p>}
              </dl>
            )}
          </Abschnitt>
        </div>
      )}

      {tab === "zeit" && (
        <div id="projekt-tabpanel-zeit" role="tabpanel" aria-labelledby="projekt-tab-zeit" className="space-y-4 p-4 pt-0">
          <ZeitSummenBlock filter={{ projekt_id: projekt.id }} />

          {zeitEintraegeAbgeschlossen.length === 0 ? (
            <p className="text-sekundaer text-label2">Keine Zeiteinträge in diesem Projekt.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-fliess">
                <thead>
                  <tr className="text-left text-label2">
                    <th className="px-2 py-1 text-meta font-medium">Techniker</th>
                    <th className="px-2 py-1 text-meta font-medium">Tätigkeit</th>
                    <th className="px-2 py-1 text-meta font-medium">Datum</th>
                    <th className="px-2 py-1 text-right text-meta font-medium">Dauer</th>
                    <th className="px-2 py-1 text-meta font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {zeitEintraegeAbgeschlossen.map((e) => {
                    const dauerSekunden = (new Date(e.ende_at!).getTime() - new Date(e.start_at).getTime()) / 1000;
                    const techniker = users?.find((u) => u.id === e.techniker_id);
                    return (
                      <tr
                        key={e.id}
                        onClick={() => setSheetEintrag(e)}
                        className="cursor-pointer border-t border-sep hover:bg-fill"
                      >
                        <td className="px-2 py-1.5 text-label">{techniker?.name ?? "—"}</td>
                        <td className="px-2 py-1.5 text-label2">
                          {e.taetigkeit || (e.vorgangsnummer ?? "—")}
                        </td>
                        <td className="px-2 py-1.5 tabular-nums text-label2">
                          {new Date(e.start_at).toLocaleDateString("de-DE", { timeZone: "Europe/Berlin" })}
                        </td>
                        <td className="px-2 py-1.5 text-right font-medium tabular-nums text-label">
                          {formatSekundenAlsHHMM(dauerSekunden)} Std.
                        </td>
                        <td className="px-2 py-1.5">
                          <StatusPille
                            status={buchungsstatusZuToken(e.buchungsstatus)}
                            label={BUCHUNGSSTATUS_LABEL[e.buchungsstatus]}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "termine" &&
        (() => {
          const heute = new Date();
          const sortiert = [...(termine ?? [])].sort(
            (a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime(),
          );
          const naechster =
            sortiert.find((t) => new Date(t.start_at).getTime() >= heute.getTime()) ?? sortiert[sortiert.length - 1];
          const referenz = naechster ? new Date(naechster.start_at) : heute;
          const wocheStart = addTage(startOfWoche(referenz), terminWocheOffset * 7);
          const wocheTage = Array.from({ length: 7 }, (_, i) => addTage(wocheStart, i));
          const wocheEnde = addTage(wocheStart, 6);
          const perTag = new Map<string, typeof sortiert>();
          for (const t of sortiert) {
            const key = tagesSchluessel(new Date(t.start_at));
            perTag.set(key, [...(perTag.get(key) ?? []), t]);
          }
          return (
            <div id="projekt-tabpanel-termine" role="tabpanel" aria-labelledby="projekt-tab-termine" className="p-4 pt-0">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => setTerminWocheOffset((o) => o - 1)}
                    className="btn-touch border rounded-[var(--radius-ap-md)] border-sep px-2 py-1 text-sekundaer text-label hover:bg-fill"
                  >
                    ← Vorherige Woche
                  </button>
                  <button
                    type="button"
                    onClick={() => setTerminWocheOffset(0)}
                    disabled={terminWocheOffset === 0}
                    className="btn-touch border rounded-[var(--radius-ap-md)] border-sep px-2 py-1 text-sekundaer text-label hover:bg-fill disabled:opacity-50"
                  >
                    Diese Woche
                  </button>
                  <button
                    type="button"
                    onClick={() => setTerminWocheOffset((o) => o + 1)}
                    className="btn-touch border rounded-[var(--radius-ap-md)] border-sep px-2 py-1 text-sekundaer text-label hover:bg-fill"
                  >
                    Nächste Woche →
                  </button>
                </div>
                <span className="text-meta text-label2">
                  {wocheStart.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })}–
                  {wocheEnde.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" })}
                </span>
              </div>
              {sortiert.length === 0 ? (
                <p className="text-sekundaer text-label2">Keine Termine in diesem Projekt.</p>
              ) : (
                <div className="grid grid-cols-7 gap-px overflow-hidden border rounded-[var(--radius-ap-md)] border-sep bg-sep">
                  {wocheTage.map((tag, i) => {
                    const heuteFlag = tagesSchluessel(tag) === tagesSchluessel(heute);
                    const eintraege = perTag.get(tagesSchluessel(tag)) ?? [];
                    return (
                      <div key={i} className="min-h-[110px] bg-card p-1.5">
                        <div className={`mb-1 text-meta font-medium ${heuteFlag ? "text-tint" : "text-label2"}`}>
                          {WOCHENTAGE[i]} {tag.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })}
                        </div>
                        <div className="space-y-1">
                          {eintraege.map((t) => (
                            <button
                              key={t.id}
                              type="button"
                              title={t.titel}
                              onClick={() => navigate(`/vorgaenge/${t.vorgang_id}/vollbild`)}
                              className={`w-full rounded-[5px] border p-1 text-left text-meta ${
                                t.status === "abgesagt" ? "border-sep text-label2 line-through" : "border-tint text-tint"
                              }`}
                            >
                              <div className="font-semibold">
                                {new Date(t.start_at).toLocaleTimeString("de-DE", {
                                  timeZone: "Europe/Berlin",
                                  hour: "2-digit",
                                  minute: "2-digit",
                                })}
                              </div>
                              <div className="truncate">{t.titel}</div>
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })()}

      {tab === "positionen" && (
        <div id="projekt-tabpanel-positionen" role="tabpanel" aria-labelledby="projekt-tab-positionen" className="p-4 pt-0">
          {!materialBedarfe || materialBedarfe.length === 0 ? (
            <p className="text-sekundaer text-label2">Keine Material-Bedarfe in diesem Projekt.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-fliess">
                <thead>
                  <tr className="text-left text-label2">
                    <th className="px-2 py-1 text-meta font-medium">Menge</th>
                    <th className="px-2 py-1 text-meta font-medium">Material</th>
                    <th className="px-2 py-1 text-meta font-medium">Vorgang</th>
                    <th className="px-2 py-1 text-meta font-medium">Zweck</th>
                    <th className="px-2 py-1 text-meta font-medium">Status</th>
                    <th className="px-2 py-1"></th>
                  </tr>
                </thead>
                <tbody>
                  {materialBedarfe.map((b) => (
                    <tr key={b.id} className="border-t border-sep">
                      <td className="px-2 py-1.5 tabular-nums text-label">{b.menge}×</td>
                      <td className="px-2 py-1.5 text-label">{b.material_bezeichnung}</td>
                      <td className="px-2 py-1.5 text-label2">
                        <button
                          onClick={() => navigate(`/vorgaenge/${b.vorgang_id}/vollbild`)}
                          className="hover:underline"
                        >
                          {b.vorgang_vorgangsnummer}
                        </button>
                      </td>
                      <td className="px-2 py-1.5 text-label2">{b.zweck === "angebot" ? "Angebot" : "Bestellung"}</td>
                      <td className="px-2 py-1.5 text-label2">{b.status}</td>
                      <td className="px-2 py-1.5 text-right">
                        {b.status === "offen" && (
                          <AktionsMenue
                            label={`Aktionen für Materialbedarf ${b.material_bezeichnung}`}
                            eintraege={[
                              {
                                label: "Entfernen",
                                icon: Trash2,
                                destruktiv: true,
                                onClick: () => bedarfEntfernenMutation.mutate(b.id),
                              },
                            ]}
                          />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {sheetEintrag && (
        <ZeiteintragSheet
          offen
          onClose={() => setSheetEintrag(null)}
          vorgangId={sheetEintrag.vorgang_id ?? ""}
          eintrag={sheetEintrag}
          onGespeichert={() => queryClient.invalidateQueries({ queryKey: ["zeiterfassung", "projekt", projekt.id] })}
        />
      )}
      {tab === "zeitplan" && <ZeitplanTab projektId={projekt.id} />}
    </SeitenPanel>
  );
}
