import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KanbanSquare } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { auftraegeApi, materialBedarfeApi, projekteApi, termineApi, usersApi, vorgaengeApi, zeiterfassungApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { ZeiteintragSheet } from "../../components/ZeiteintragSheet";
import { ZeitSummenBlock } from "../../components/ZeitSummenBlock";
import { SeitenPanel } from "../../components/apple/SeitenPanel";
import { StatusPille } from "../../components/apple/StatusPille";
import { AUFTRAG_STATUS_LABEL } from "../auftraege/AuftraegeTabelle";
import { STATUS_BADGE, STATUS_LABEL } from "../../config/vorgangDarstellung";
import type { Projekt, Zeiterfassung } from "../../types";
import { formatSekundenAlsHHMM } from "../../utils/duration";
import { BUCHUNGSSTATUS_LABEL, buchungsstatusZuToken } from "../../utils/zeiterfassung";
import { KennzahlKarte } from "../OfficeUi";

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
  return d.toISOString().slice(0, 10);
}

const TABS: { key: "uebersicht" | "zeit" | "termine" | "positionen"; label: string }[] = [
  { key: "uebersicht", label: "Übersicht" },
  { key: "zeit", label: "Zeit" },
  { key: "termine", label: "Termine" },
  { key: "positionen", label: "Positionen" },
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
  onClose,
  onKanbanOeffnen,
}: {
  projekt: Projekt;
  onClose: () => void;
  onKanbanOeffnen: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState(projekt.name);
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("uebersicht");
  const [terminWocheOffset, setTerminWocheOffset] = useState(0);
  const [sheetEintrag, setSheetEintrag] = useState<Zeiterfassung | null>(null);

  const { data: aktuell } = useQuery({
    queryKey: ["projekte", projekt.id],
    queryFn: () => projekteApi.get(projekt.id),
    initialData: projekt,
  });

  const { data: auftraege } = useQuery({
    queryKey: ["auftraege", "projekt", projekt.id],
    queryFn: () => auftraegeApi.list({ projekt_id: projekt.id }),
  });

  const { data: vorgaenge } = useQuery({
    queryKey: ["vorgaenge", "projekt", projekt.id],
    queryFn: () => vorgaengeApi.list({ projekt_id: projekt.id }),
  });

  const { data: users } = useQuery({ queryKey: ["users"], queryFn: usersApi.list, enabled: tab === "zeit" });

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
    },
  });

  const bedarfEntfernenMutation = useMutation({
    mutationFn: (id: string) => materialBedarfeApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["material-bedarfe", "projekt", projekt.id] }),
  });

  const zeitEintraegeAbgeschlossen = (zeiterfassungListe ?? [])
    .filter((e) => e.ende_at)
    .sort((a, b) => new Date(b.start_at).getTime() - new Date(a.start_at).getTime());

  return (
    <SeitenPanel
      offen
      titel={aktuell?.name ?? projekt.name}
      onClose={onClose}
      aktionen={
        <button onClick={onKanbanOeffnen} className="btn-ap flex items-center gap-1.5 text-xs">
          <KanbanSquare size={14} strokeWidth={2} aria-hidden="true" />
          Kanban öffnen
        </button>
      }
    >
      <div
        role="tablist"
        aria-label="Projekt-Abschnitte"
        className="mb-3 flex gap-1 overflow-x-auto border-b border-sep px-4 pt-3 pb-2 text-sm"
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
          className="space-y-5 p-4 pt-0"
        >
          <div className="grid grid-cols-2 gap-3">
            <KennzahlKarte label="Aufträge" wert={String(auftraege?.length ?? 0)} />
            <KennzahlKarte label="Vorgänge" wert={String(vorgaenge?.length ?? 0)} />
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => name.trim() && name !== aktuell?.name && aktualisieren.mutate({ name: name.trim() })}
              className="field-ap"
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-label">
            <input
              type="checkbox"
              checked={aktuell?.archiviert ?? projekt.archiviert}
              onChange={(e) => aktualisieren.mutate({ archiviert: e.target.checked })}
              className="h-4 w-4"
            />
            Archiviert
          </label>

          <div>
            <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">
              Aufträge ({auftraege?.length ?? 0})
            </label>
            {!auftraege || auftraege.length === 0 ? (
              <EmptyState icon={KanbanSquare} text="Noch kein Auftrag in diesem Projekt." />
            ) : (
              <div className="space-y-1.5">
                {auftraege.map((a) => (
                  <div key={a.id} className="flex items-center justify-between gap-2 border border-sepstrong px-2.5 py-2 text-sm">
                    <span className="min-w-0 flex-1 truncate text-label">{a.titel}</span>
                    <span className="shrink-0 text-xs text-label2">{AUFTRAG_STATUS_LABEL[a.status]}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label className="block text-[11px] font-bold tracking-wide text-label3 uppercase">
                Vorgänge direkt am Projekt ({vorgaenge?.length ?? 0})
              </label>
              <button
                onClick={() => navigate(`/neu?projekt_id=${projekt.id}`)}
                className="text-xs font-medium text-tint hover:underline"
              >
                + Neuer Vorgang
              </button>
            </div>
            {!vorgaenge || vorgaenge.length === 0 ? (
              <p className="text-sm text-label2">Keine Vorgänge direkt zugeordnet.</p>
            ) : (
              <div className="space-y-1.5">
                {vorgaenge.map((v) => (
                  <button
                    key={v.id}
                    onClick={() => navigate(`/vorgaenge/${v.id}`)}
                    className="flex w-full items-center justify-between gap-2 border border-sepstrong px-2.5 py-2 text-left text-sm hover:bg-fill"
                  >
                    <span className="min-w-0 flex-1 truncate text-label">
                      {v.vorgangsnummer} · {v.titel}
                    </span>
                    <span className={`shrink-0 rounded-[var(--radius-ap-pill)] px-2 py-0.5 text-[11px] font-semibold ${STATUS_BADGE[v.status]}`}>
                      {STATUS_LABEL[v.status]}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "zeit" && (
        <div id="projekt-tabpanel-zeit" role="tabpanel" aria-labelledby="projekt-tab-zeit" className="space-y-4 p-4 pt-0">
          <ZeitSummenBlock filter={{ projekt_id: projekt.id }} />

          {zeitEintraegeAbgeschlossen.length === 0 ? (
            <p className="text-sm text-label2">Keine Zeiteinträge in diesem Projekt.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="text-left text-label2">
                    <th className="px-2 py-1 text-xs font-medium">Techniker</th>
                    <th className="px-2 py-1 text-xs font-medium">Tätigkeit</th>
                    <th className="px-2 py-1 text-xs font-medium">Datum</th>
                    <th className="px-2 py-1 text-right text-xs font-medium">Dauer</th>
                    <th className="px-2 py-1 text-xs font-medium">Status</th>
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
                    className="btn-touch border border-sep px-2 py-1 text-xs text-label hover:bg-fill"
                  >
                    ← Vorherige Woche
                  </button>
                  <button
                    type="button"
                    onClick={() => setTerminWocheOffset(0)}
                    disabled={terminWocheOffset === 0}
                    className="btn-touch border border-sep px-2 py-1 text-xs text-label hover:bg-fill disabled:opacity-50"
                  >
                    Diese Woche
                  </button>
                  <button
                    type="button"
                    onClick={() => setTerminWocheOffset((o) => o + 1)}
                    className="btn-touch border border-sep px-2 py-1 text-xs text-label hover:bg-fill"
                  >
                    Nächste Woche →
                  </button>
                </div>
                <span className="text-xs text-label2">
                  {wocheStart.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })}–
                  {wocheEnde.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" })}
                </span>
              </div>
              {sortiert.length === 0 ? (
                <p className="text-sm text-label2">Keine Termine in diesem Projekt.</p>
              ) : (
                <div className="grid grid-cols-7 gap-px overflow-hidden border border-sep bg-sep">
                  {wocheTage.map((tag, i) => {
                    const heuteFlag = tagesSchluessel(tag) === tagesSchluessel(heute);
                    const eintraege = perTag.get(tagesSchluessel(tag)) ?? [];
                    return (
                      <div key={i} className="min-h-[110px] bg-card p-1.5">
                        <div className={`mb-1 text-[11px] font-medium ${heuteFlag ? "text-tint" : "text-label2"}`}>
                          {WOCHENTAGE[i]} {tag.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })}
                        </div>
                        <div className="space-y-1">
                          {eintraege.map((t) => (
                            <button
                              key={t.id}
                              type="button"
                              title={t.titel}
                              onClick={() => navigate(`/vorgaenge/${t.vorgang_id}`)}
                              className={`w-full rounded-[5px] border p-1 text-left text-[11px] ${
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
            <p className="text-sm text-label2">Keine Material-Bedarfe in diesem Projekt.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="text-left text-label2">
                    <th className="px-2 py-1 text-xs font-medium">Menge</th>
                    <th className="px-2 py-1 text-xs font-medium">Material</th>
                    <th className="px-2 py-1 text-xs font-medium">Vorgang</th>
                    <th className="px-2 py-1 text-xs font-medium">Zweck</th>
                    <th className="px-2 py-1 text-xs font-medium">Status</th>
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
                          onClick={() => navigate(`/vorgaenge/${b.vorgang_id}`)}
                          className="hover:underline"
                        >
                          {b.vorgang_vorgangsnummer}
                        </button>
                      </td>
                      <td className="px-2 py-1.5 text-label2">{b.zweck === "angebot" ? "Angebot" : "Bestellung"}</td>
                      <td className="px-2 py-1.5 text-label2">{b.status}</td>
                      <td className="px-2 py-1.5 text-right">
                        {b.status === "offen" && (
                          <button
                            onClick={() => bedarfEntfernenMutation.mutate(b.id)}
                            className="btn-touch text-xs text-st-fehlt"
                          >
                            Entfernen
                          </button>
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
    </SeitenPanel>
  );
}
