import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftToLine,
  ArrowRightToLine,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  LayoutGrid,
  LayoutDashboard,
  Pencil,
  Plus,
  Share2,
  Trash2,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { exportApi, kennzahlenApi } from "../../api/endpoints";
import { AktionsMenue, type AktionsMenueEintrag } from "../../components/AktionsMenue";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { Skeleton } from "../../components/Skeleton";
import { fehlerText, useToast } from "../../components/Toast";
import { Select } from "../../components/apple/Select";
import { sichtbareNavSeiten, type WorkspaceKey, verfuegbareWorkspaces } from "../../config/navSeiten";
import { useAuth } from "../../context/AuthContext";
import type {
  DashboardLayout,
  DashboardWidget,
  DashboardZeitraum,
  KennzahlDef,
  KennzahlenDashboard,
  WidgetGroesse,
} from "../../types/kennzahlen";
import { downloadBlob } from "../../utils/download";
import { istAdminRolle } from "../../utils/rollen";
import { WORKSPACE_STORAGE_KEY, fuerOffice, workspaceFuerRoute } from "../navAktiv";
import { SeitenKopf } from "../OfficeUi";
import { DashboardNamePanel, NAME_MAX } from "./DashboardNamePanel";
import { DashboardRaster } from "./DashboardRaster";
import { standardDarstellung } from "./darstellungen";
import { KatalogPanel, MAX_WIDGETS } from "./KatalogPanel";
import { VORLAGEN, vorlageFuerKatalog, type Vorlage, type VorlagenSchluessel } from "./vorlagen";
import { WidgetEinstellungen } from "./WidgetEinstellungen";
import { WidgetKarte } from "./WidgetKarte";
import {
  ZEITRAUM_OPTIONEN,
  verschieben,
  zeitraumBerechnen,
  zeitraumEnthaeltHeute,
} from "./zeitraum";

// Eigenes Dashboard je Nutzer merken (wie die Kachel-Auswahl der Arbeitszeit): reine Geräte-Präferenz.
const letztesKey = (userId: string) => `kennzahlen.letztes.${userId}`;

// Startdashboard je Workspace, solange noch nichts gemerkt ist.
const WORKSPACE_START: Record<WorkspaceKey, VorlagenSchluessel> = {
  operativ: "vorgaenge",
  sales: "ueberblick",
  finanzen: "finanzen",
  verwaltung: "team",
};

const EXPORTE = [
  { label: "Vorgänge (CSV)", datei: "Vorgaenge.csv", abruf: exportApi.vorgaengeCsv },
  { label: "Arbeitszeit (CSV)", datei: "Zeiterfassung.csv", abruf: exportApi.zeiterfassungCsv },
  { label: "Material-Bestand (CSV)", datei: "Material-Bestand.csv", abruf: exportApi.materialCsv },
  { label: "Eingangsrechnungen (CSV)", datei: "Eingangsrechnungen.csv", abruf: exportApi.eingangsrechnungenCsv },
];

interface TabEintrag {
  /** Vorlagenschlüssel oder Dashboard-id: das, was in `?dashboard=` steht. */
  schluessel: string;
  name: string;
  layout: DashboardLayout;
  vorlage: Vorlage | null;
  dashboard: KennzahlenDashboard | null;
}

/** Bearbeitungsstand. dashboardId gesetzt = eigenes Dashboard (Speichern per PATCH), sonst wird eine Kopie angelegt (POST). */
interface Entwurf {
  dashboardId: string | null;
  name: string;
  vorlage: string | null;
  layout: DashboardLayout;
  hinweis: string | null;
}

function neueWidgetId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `w-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

/** "<Name> (eigene)", bei Konflikt "(eigene 2)" ...: Der Server lehnt doppelte Namen je Nutzer ab (409). */
export function eindeutigerKopieName(basis: string, vorhandene: string[]): string {
  const belegt = new Set(vorhandene.map((n) => n.toLocaleLowerCase("de-DE")));
  for (let n = 1; ; n += 1) {
    const suffix = n === 1 ? " (eigene)" : ` (eigene ${n})`;
    const kandidat = `${basis.slice(0, NAME_MAX - suffix.length)}${suffix}`;
    if (!belegt.has(kandidat.toLocaleLowerCase("de-DE"))) return kandidat;
  }
}

function gemerkt(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    // Privater Modus o. ä.: dann gilt das Startdashboard.
    return null;
  }
}

function merken(key: string, wert: string) {
  try {
    localStorage.setItem(key, wert);
  } catch {
    // Nur eine Komfortfunktion, kein Fehler wert.
  }
}

export function KennzahlenPage() {
  const { currentUser, hatRecht } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToast();
  const bestaetigen = useBestaetigung();
  const [params, setParams] = useSearchParams();

  const katalogQuery = useQuery({
    queryKey: ["kennzahlen-katalog"],
    queryFn: kennzahlenApi.katalog,
    staleTime: 5 * 60 * 1000,
  });
  const dashboardsQuery = useQuery({
    queryKey: ["kennzahlen-dashboards"],
    queryFn: kennzahlenApi.dashboards,
  });

  const [entwurf, setEntwurf] = useState<Entwurf | null>(null);
  const [ausgewaehlt, setAusgewaehlt] = useState<string | null>(null);
  const [namePanel, setNamePanel] = useState<"neu" | "umbenennen" | null>(null);
  // Zeitraumwahl der Sitzung je Dashboard; ein Wechsel des Tabs verwirft sie (Schlüsselvergleich statt Zurücksetzen per Effekt).
  const [zeit, setZeit] = useState<{ key: string; art: DashboardZeitraum | null; anker: Date } | null>(null);
  const heute = useMemo(() => new Date(), []);

  const katalog = katalogQuery.data;
  const katalogMap = useMemo(() => new Map((katalog ?? []).map((d) => [d.schluessel, d])), [katalog]);

  const tabs = useMemo<TabEintrag[]>(() => {
    if (!katalog) return [];
    const schluessel = new Set(katalog.map((d) => d.schluessel));
    const vorlagen = VORLAGEN.flatMap((v) => {
      const gekuerzt = vorlageFuerKatalog(v, schluessel);
      return gekuerzt ? [{ schluessel: v.schluessel, name: v.name, layout: gekuerzt.layout, vorlage: gekuerzt, dashboard: null }] : [];
    });
    const eigene = (dashboardsQuery.data ?? []).filter((d) => d.eigenes);
    const fremde = (dashboardsQuery.data ?? []).filter((d) => !d.eigenes);
    const alsTab = (d: KennzahlenDashboard): TabEintrag => ({
      schluessel: d.id,
      name: d.name,
      layout: d.layout,
      vorlage: null,
      dashboard: d,
    });
    return [...vorlagen, ...eigene.map(alsTab), ...fremde.map(alsTab)];
  }, [katalog, dashboardsQuery.data]);

  const workspaceStart = useMemo(() => {
    const sichtbar = fuerOffice(sichtbareNavSeiten(currentUser, hatRecht));
    const workspaces = verfuegbareWorkspaces(sichtbar);
    const seite = sichtbar.find((s) => s.key === "kennzahlen");
    const workspace = workspaceFuerRoute(seite, workspaces, gemerkt(WORKSPACE_STORAGE_KEY));
    return workspace ? WORKSPACE_START[workspace.key] : undefined;
  }, [currentUser, hatRecht]);

  const userId = currentUser?.id ?? "";
  const aktiv: TabEintrag | undefined = useMemo(() => {
    const finde = (key: string | null | undefined) => (key ? tabs.find((t) => t.schluessel === key) : undefined);
    return (
      finde(params.get("dashboard")) ??
      finde(gemerkt(letztesKey(userId))) ??
      finde(workspaceStart) ??
      finde("ueberblick") ??
      tabs[0]
    );
  }, [tabs, params, userId, workspaceStart]);

  const aktivKey = aktiv?.schluessel;
  useEffect(() => {
    if (aktivKey) merken(letztesKey(userId), aktivKey);
  }, [aktivKey, userId]);

  const bearbeiten = entwurf !== null;
  const sitzung = zeit && zeit.key === aktivKey ? zeit : null;
  const anker = sitzung?.anker ?? heute;
  const zeitraumArt: DashboardZeitraum = entwurf?.layout.zeitraum ?? sitzung?.art ?? aktiv?.layout.zeitraum ?? "monat";
  const zeitraum = useMemo(() => zeitraumBerechnen(zeitraumArt, anker), [zeitraumArt, anker]);
  const widgets = entwurf ? entwurf.layout.widgets : (aktiv?.layout.widgets ?? []);
  const eigeneNamen = (dashboardsQuery.data ?? []).filter((d) => d.eigenes).map((d) => d.name);
  const eigeneIds = (dashboardsQuery.data ?? []).filter((d) => d.eigenes).map((d) => d.id);
  const ausgewaehltesWidget = widgets.find((w) => w.id === ausgewaehlt) ?? null;

  // --- Mutationen ---------------------------------------------------------------------------------------------

  const aktualisiereListe = async () => {
    await queryClient.invalidateQueries({ queryKey: ["kennzahlen-dashboards"] });
  };

  const speichern = useMutation({
    mutationFn: (e: Entwurf) =>
      e.dashboardId
        ? kennzahlenApi.dashboardAendern(e.dashboardId, { layout: e.layout })
        : kennzahlenApi.dashboardAnlegen({ name: e.name, layout: e.layout, vorlage: e.vorlage }),
    onSuccess: async (dashboard) => {
      // Erst die Liste neu laden, dann umschalten: sonst kennt der Tab-Schlüssel das neue Dashboard noch nicht.
      await aktualisiereListe();
      setParams({ dashboard: dashboard.id }, { replace: true });
      setEntwurf(null);
      setAusgewaehlt(null);
      toast.erfolg("Dashboard gespeichert");
    },
    onError: (err) =>
      toast.fehler(
        err instanceof ApiError && err.status === 409
          ? "Ein Dashboard mit diesem Namen gibt es schon."
          : fehlerText(err, "Dashboard konnte nicht gespeichert werden."),
      ),
  });

  const aendern = useMutation({
    mutationFn: ({ id, ...body }: { id: string; name?: string; fuer_alle?: boolean }) =>
      kennzahlenApi.dashboardAendern(id, body),
    onSuccess: aktualisiereListe,
    // Fehler zeigt der Aufrufer selbst (Umbenennen am Feld, Freigabe als Toast), nicht zusätzlich der zentrale Handler.
    meta: { stumm: true },
  });

  const loeschen = useMutation({
    mutationFn: (id: string) => kennzahlenApi.dashboardLoeschen(id),
    onSuccess: async () => {
      await aktualisiereListe();
      setParams({}, { replace: true });
      toast.erfolg("Dashboard gelöscht");
    },
  });

  const umsortieren = useMutation({
    mutationFn: (ids: string[]) => kennzahlenApi.reihenfolge(ids),
    onSuccess: aktualisiereListe,
  });

  const exportieren = useMutation({
    mutationFn: async (export_: (typeof EXPORTE)[number]) => ({ blob: await export_.abruf(), datei: export_.datei }),
    onSuccess: ({ blob, datei }) => downloadBlob(blob, datei),
  });

  // --- Aktionen -----------------------------------------------------------------------------------------------

  function tabWaehlen(key: string) {
    setParams({ dashboard: key }, { replace: true });
  }

  function anpassenStarten(widgetId?: string) {
    if (!aktiv) return;
    const layout: DashboardLayout = { zeitraum: zeitraumArt, widgets: aktiv.layout.widgets.map((w) => ({ ...w })) };
    if (aktiv.dashboard?.eigenes) {
      setEntwurf({ dashboardId: aktiv.dashboard.id, name: aktiv.name, vorlage: aktiv.dashboard.vorlage, layout, hinweis: null });
    } else {
      // Vorlagen und fremde geteilte Dashboards bleiben unverändert: "Anpassen" arbeitet auf einer eigenen Kopie.
      setEntwurf({
        dashboardId: null,
        name: eindeutigerKopieName(aktiv.name, eigeneNamen),
        vorlage: aktiv.vorlage?.schluessel ?? aktiv.dashboard?.vorlage ?? null,
        layout,
        hinweis: `Persönliche Kopie von „${aktiv.name}“`,
      });
    }
    setAusgewaehlt(widgetId ?? null);
  }

  function bearbeitenBeenden() {
    setEntwurf(null);
    setAusgewaehlt(null);
  }

  function widgetsAendern(aendern_: (liste: DashboardWidget[]) => DashboardWidget[]) {
    setEntwurf((alt) => (alt ? { ...alt, layout: { ...alt.layout, widgets: aendern_(alt.layout.widgets) } } : alt));
  }

  function widgetAendern(id: string, patch: Partial<DashboardWidget>) {
    widgetsAendern((liste) => liste.map((w) => (w.id === id ? { ...w, ...patch } : w)));
  }

  function widgetEntfernen(id: string) {
    widgetsAendern((liste) => liste.filter((w) => w.id !== id));
    setAusgewaehlt((alt) => (alt === id ? null : alt));
  }

  function widgetHinzufuegen(def: KennzahlDef) {
    if (widgets.length >= MAX_WIDGETS) return;
    const widget: DashboardWidget = {
      id: neueWidgetId(),
      kennzahl: def.schluessel,
      darstellung: standardDarstellung(def),
      gruppierung: null,
      groesse: "s",
      titel: null,
      vergleich: def.art === "zeitraum",
    };
    widgetsAendern((liste) => [...liste, widget]);
    setAusgewaehlt(widget.id);
  }

  function reihenfolgeAendern(ids: string[]) {
    widgetsAendern((liste) => ids.flatMap((id) => liste.filter((w) => w.id === id)));
  }

  function artWechseln(art: DashboardZeitraum) {
    if (entwurf) {
      setEntwurf({ ...entwurf, layout: { ...entwurf.layout, zeitraum: art } });
    } else if (aktivKey) {
      setZeit({ key: aktivKey, art, anker });
    }
  }

  function zeitraumVerschieben(schritt: 1 | -1) {
    if (aktivKey) setZeit({ key: aktivKey, art: sitzung?.art ?? null, anker: verschieben(zeitraumArt, anker, schritt) });
  }

  async function dashboardLoeschen(tab: TabEintrag) {
    if (!tab.dashboard) return;
    const ok = await bestaetigen({
      titel: "Dashboard löschen?",
      text: tab.dashboard.fuer_alle
        ? `„${tab.name}“ ist für alle freigegeben und verschwindet dann bei allen im Betrieb.`
        : `„${tab.name}“ wird endgültig gelöscht.`,
      bestaetigenLabel: "Löschen",
    });
    if (ok) loeschen.mutate(tab.dashboard.id);
  }

  function verschiebenImTab(tab: TabEintrag, richtung: -1 | 1) {
    const index = eigeneIds.indexOf(tab.schluessel);
    const ziel = index + richtung;
    if (index < 0 || ziel < 0 || ziel >= eigeneIds.length) return;
    const ids = [...eigeneIds];
    [ids[index], ids[ziel]] = [ids[ziel], ids[index]];
    umsortieren.mutate(ids);
  }

  async function neuesDashboard(name: string, startMit: string) {
    const vorlage = tabs.find((t) => t.vorlage?.schluessel === startMit)?.vorlage ?? null;
    const layout: DashboardLayout = vorlage
      ? { zeitraum: vorlage.layout.zeitraum, widgets: vorlage.layout.widgets.map((w) => ({ ...w })) }
      : { zeitraum: "monat", widgets: [] };
    const neu = await kennzahlenApi.dashboardAnlegen({ name, layout, vorlage: vorlage?.schluessel ?? null });
    await aktualisiereListe();
    setParams({ dashboard: neu.id }, { replace: true });
    setEntwurf({ dashboardId: neu.id, name: neu.name, vorlage: neu.vorlage, layout: neu.layout, hinweis: null });
    setAusgewaehlt(null);
  }

  // --- Darstellung --------------------------------------------------------------------------------------------

  const istMandantAdmin = currentUser?.role === "mandant_admin";
  const eigenerTab = !!aktiv?.dashboard?.eigenes;

  const tabMenue: (AktionsMenueEintrag | "trenner")[] =
    aktiv && aktiv.dashboard && eigenerTab
      ? [
          { label: "Umbenennen", icon: Pencil, onClick: () => setNamePanel("umbenennen") },
          ...(istMandantAdmin
            ? [
                {
                  label: aktiv.dashboard.fuer_alle ? "Freigabe aufheben" : "Für alle freigeben",
                  icon: Share2,
                  onClick: () => {
                    const dashboard = aktiv.dashboard!;
                    aendern.mutate(
                      { id: dashboard.id, fuer_alle: !dashboard.fuer_alle },
                      {
                        onSuccess: () => toast.erfolg(dashboard.fuer_alle ? "Freigabe aufgehoben" : "Für alle freigegeben"),
                        onError: (err) => toast.fehler(fehlerText(err, "Freigabe konnte nicht geändert werden.")),
                      },
                    );
                  },
                },
              ]
            : []),
          {
            label: "Nach links",
            icon: ArrowLeftToLine,
            disabled: eigeneIds.indexOf(aktiv.schluessel) <= 0,
            onClick: () => verschiebenImTab(aktiv, -1),
          },
          {
            label: "Nach rechts",
            icon: ArrowRightToLine,
            disabled: eigeneIds.indexOf(aktiv.schluessel) >= eigeneIds.length - 1,
            onClick: () => verschiebenImTab(aktiv, 1),
          },
          "trenner",
          { label: "Löschen", icon: Trash2, destruktiv: true, onClick: () => dashboardLoeschen(aktiv) },
        ]
      : [];

  const exportMenue: AktionsMenueEintrag[] = EXPORTE.map((e) => ({
    label: e.label,
    icon: Download,
    onClick: () => exportieren.mutate(e),
  }));

  const ladeFehler = katalogQuery.error ?? dashboardsQuery.error;
  const laedt = katalogQuery.isLoading || dashboardsQuery.isLoading;

  const kopfAktionen = (
    <>
      <div className="flex items-center gap-1">
        <Select
          aria-label="Zeitraum"
          groesse="kompakt"
          className="w-[10.5rem]"
          value={zeitraumArt}
          onChange={(e) => artWechseln(e.target.value as DashboardZeitraum)}
        >
          {ZEITRAUM_OPTIONEN.map((o) => (
            <option key={o.wert} value={o.wert}>
              {o.label}
            </option>
          ))}
        </Select>
        <button type="button" className="btn-ap-toolbar" aria-label="Vorheriger Zeitraum" onClick={() => zeitraumVerschieben(-1)}>
          <ChevronLeft size={16} strokeWidth={2} aria-hidden="true" />
        </button>
        <span aria-live="polite" className="min-w-32 text-center text-sekundaer font-semibold text-label">
          {zeitraum.label}
        </span>
        <button
          type="button"
          className="btn-ap-toolbar"
          aria-label="Nächster Zeitraum"
          disabled={zeitraumEnthaeltHeute(zeitraumArt, anker, heute)}
          onClick={() => zeitraumVerschieben(1)}
        >
          <ChevronRight size={16} strokeWidth={2} aria-hidden="true" />
        </button>
      </div>

      {bearbeiten ? (
        <>
          <button type="button" className="btn-ap px-3" onClick={bearbeitenBeenden} disabled={speichern.isPending}>
            Abbrechen
          </button>
          <button
            type="button"
            className="btn-ap-primary px-4"
            onClick={() => entwurf && speichern.mutate(entwurf)}
            disabled={speichern.isPending}
          >
            <Check size={14} strokeWidth={2.5} aria-hidden="true" /> Fertig
          </button>
        </>
      ) : (
        <>
          {istAdminRolle(currentUser) && (
            <AktionsMenue
              label="Export"
              eintraege={exportMenue}
              ausloeser={() => (
                <span className="btn-ap px-3">
                  <Download size={14} strokeWidth={2} aria-hidden="true" /> Export
                  <ChevronDown size={13} strokeWidth={2} aria-hidden="true" />
                </span>
              )}
            />
          )}
          <button type="button" className="btn-ap-primary px-4" onClick={() => anpassenStarten()} disabled={!aktiv}>
            <LayoutGrid size={14} strokeWidth={2} aria-hidden="true" /> Anpassen
          </button>
        </>
      )}
    </>
  );

  return (
    <div>
      <SeitenKopf titel="Kennzahlen">{aktiv ? kopfAktionen : null}</SeitenKopf>

      {ladeFehler && (!katalog || !dashboardsQuery.data) ? (
        <FehlerZustand
          fehler={ladeFehler}
          was="Die Kennzahlen"
          className="py-6"
          onErneut={() => {
            void katalogQuery.refetch();
            void dashboardsQuery.refetch();
          }}
        />
      ) : laedt ? (
        <div role="status" aria-busy="true" className="grid grid-cols-12 gap-4">
          <span className="sr-only">Lädt…</span>
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="col-span-12 h-32 md:col-span-6 xl:col-span-3" />
          ))}
        </div>
      ) : !aktiv ? (
        <EmptyState
          icon={LayoutDashboard}
          text="Es sind keine Kennzahlen für dich freigegeben. Dein Administrator kann Rechte vergeben."
          className="py-16"
        />
      ) : (
        <>
          <div className="flex items-end gap-2 border-b-[0.5px] border-sepstrong">
            <div role="tablist" aria-label="Dashboards" className="flex min-w-0 gap-5 overflow-x-auto">
              {tabs.map((tab) => {
                const aktivTab = tab.schluessel === aktiv.schluessel;
                const geteilt = !!tab.dashboard && !tab.dashboard.eigenes;
                return (
                  <button
                    key={tab.schluessel}
                    type="button"
                    role="tab"
                    id={`tab-${tab.schluessel}`}
                    aria-selected={aktivTab}
                    aria-controls="kennzahlen-inhalt"
                    disabled={bearbeiten && !aktivTab}
                    title={geteilt ? `Geteilt von ${tab.dashboard?.ersteller_name}` : undefined}
                    onClick={() => tabWaehlen(tab.schluessel)}
                    className={`-mb-[0.5px] inline-flex items-center gap-1.5 border-b-2 px-0.5 pb-2 text-fliess font-semibold whitespace-nowrap disabled:opacity-40 ${
                      aktivTab ? "border-tint text-tint-text" : "border-transparent text-label2 hover:text-label"
                    }`}
                  >
                    {geteilt && <Users size={13} strokeWidth={2} aria-hidden="true" />}
                    {tab.name}
                    {geteilt && <span className="sr-only"> (geteilt von {tab.dashboard?.ersteller_name})</span>}
                  </button>
                );
              })}
            </div>
            {!bearbeiten && (
              <div className="mb-1 flex shrink-0 items-center gap-0.5">
                <button type="button" className="btn-ap-toolbar" aria-label="Neues Dashboard" title="Neues Dashboard" onClick={() => setNamePanel("neu")}>
                  <Plus size={16} strokeWidth={2} aria-hidden="true" />
                </button>
                {tabMenue.length > 0 && <AktionsMenue label={`Aktionen für ${aktiv.name}`} eintraege={tabMenue} />}
              </div>
            )}
            {entwurf?.hinweis && (
              <p className="mb-2 ml-auto text-sekundaer text-label2">{entwurf.hinweis} · Ziehen zum Sortieren, Größe oben rechts</p>
            )}
          </div>

          <div className="mt-4 flex flex-col gap-4 lg:flex-row lg:items-start">
            <div id="kennzahlen-inhalt" role="tabpanel" aria-labelledby={`tab-${aktiv.schluessel}`} className="min-w-0 flex-1">
              {widgets.length === 0 ? (
                <EmptyState
                  icon={LayoutDashboard}
                  text={bearbeiten ? "Noch keine Kennzahlen. Füge rechts welche hinzu." : "Dieses Dashboard ist noch leer. Mit „Anpassen“ kannst du Kennzahlen hinzufügen."}
                  className="py-16"
                />
              ) : (
                <DashboardRaster
                  widgets={widgets}
                  bearbeiten={bearbeiten}
                  onReihenfolge={reihenfolgeAendern}
                  renderWidget={(widget, { griff }) => (
                    <WidgetKarte
                      widget={widget}
                      def={katalogMap.get(widget.kennzahl) ?? null}
                      zeitraumArt={zeitraumArt}
                      zeitraum={zeitraum}
                      bearbeiten={bearbeiten}
                      ausgewaehlt={ausgewaehlt === widget.id}
                      griff={griff}
                      onAuswaehlen={() => setAusgewaehlt(widget.id)}
                      onGroesse={(groesse: WidgetGroesse) => widgetAendern(widget.id, { groesse })}
                      onEntfernen={() => widgetEntfernen(widget.id)}
                      onDarstellungAendern={() => anpassenStarten(widget.id)}
                    />
                  )}
                />
              )}
            </div>

            {bearbeiten &&
              (ausgewaehltesWidget ? (
                <WidgetEinstellungen
                  widget={ausgewaehltesWidget}
                  def={katalogMap.get(ausgewaehltesWidget.kennzahl) ?? null}
                  onAendern={(patch) => widgetAendern(ausgewaehltesWidget.id, patch)}
                  onZurueck={() => setAusgewaehlt(null)}
                  onEntfernen={() => widgetEntfernen(ausgewaehltesWidget.id)}
                />
              ) : (
                <KatalogPanel katalog={katalog ?? []} anzahlWidgets={widgets.length} onHinzufuegen={widgetHinzufuegen} />
              ))}
          </div>
        </>
      )}

      {namePanel === "neu" && (
        <DashboardNamePanel
          modus="neu"
          vorlagen={tabs.filter((t) => t.vorlage).map((t) => ({ schluessel: t.schluessel, name: t.name }))}
          onClose={() => setNamePanel(null)}
          onSpeichern={neuesDashboard}
        />
      )}
      {namePanel === "umbenennen" && aktiv?.dashboard && (
        <DashboardNamePanel
          modus="umbenennen"
          anfangsName={aktiv.dashboard.name}
          onClose={() => setNamePanel(null)}
          onSpeichern={async (name) => {
            await aendern.mutateAsync({ id: aktiv.dashboard!.id, name });
          }}
        />
      )}
    </div>
  );
}
