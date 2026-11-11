import { useQuery } from "@tanstack/react-query";
import { heuteIso } from "../utils/format";
import {
  Bug,
  CalendarDays,
  ChevronDown,
  ChevronUp,
  ClipboardList,
  Clock,
  Flag,
  Folder,
  FolderCog,
  Inbox,
  Lightbulb,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  Smartphone,
} from "lucide-react";
import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";

import { navKategorienApi, projekteApi, statistikApi, vorgaengeApi } from "../api/endpoints";
import { useFehlerbericht } from "../bugreport/ui";
import { ImpersonationBanner } from "../components/ImpersonationBanner";
import { Monogramm } from "../components/apple/Monogramm";
import { Logo } from "../components/brand/Logo";
import { AktionsMenue, type AktionsMenueEintrag } from "../components/AktionsMenue";
import { ThemeToggle } from "../components/ThemeToggle";
import {
  effektiveNavGruppen,
  seiteInWorkspace,
  sichtbareNavSeiten,
  verfuegbareWorkspaces,
  workspaceStartRoute,
  type WorkspaceKey,
} from "../config/navSeiten";
import { useAuth } from "../context/AuthContext";
import { useAppLiveDaten } from "../hooks/useAppLiveDaten";
import { useVorgemerkteZeitenAnzahl } from "../hooks/useVorgemerkteZeitenAnzahl";
import { weicheAus } from "./geraeteWeiche";
import { mobileUrl } from "./hostname";
import { aktiverNavKey, fuerOffice, workspaceFuerRoute } from "./navAktiv";
import { SeitenGrenze } from "../components/ErrorBoundary";

/** Die Seitenleiste wird vollstaendig aus config/navSeiten.ts erzeugt --
 * dieselbe Quelle, aus der die Tab-Bar der Handy-App gespeist wird. Damit
 * kann eine neue Seite nicht in der einen Oberflaeche auftauchen und in der
 * anderen fehlen, und die sichtbar()-Praedikate (Rechte + aktive Module)
 * gelten hier automatisch mit. */
const SIDEBAR_STORAGE_KEY = "fieldvibe-office-sidebar-eingeklappt";
const WORKSPACE_STORAGE_KEY = "fieldvibe-office-workspace";
const KATEGORIEN_STORAGE_KEY = "fieldvibe-office-sidebar-kategorien-eingeklappt";

function geladeneEingeklappteKategorien(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(KATEGORIEN_STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

const ROLLE_LABEL: Record<string, string> = {
  super_admin: "Super-Admin",
  mandant_admin: "Administrator",
  loesch_ansicht: "Papierkorb (Ansicht)",
  loesch_operativ: "Papierkorb (Verwaltung)",
};

const ZAEHL_LIMIT = 200;
const ERLEDIGTE_STATUS = ["abgeschlossen", "abgerechnet", "storniert"];

/** Offene Vorgaenge im Faelligkeitsfenster. Es gibt keinen Zaehl-Endpoint --
 * gezaehlt wird die Treffermenge der Listen-Route (Backend-Limit 200), bei
 * Erreichen des Limits zeigt die Kachel "200+" statt einer falschen Zahl. */
function useOffeneAnzahl(
  schluessel: string,
  params: Record<string, string>,
  enabled: boolean,
): { anzahl: number | undefined; gekappt: boolean } {
  const { data } = useQuery({
    queryKey: ["vorgang-anzahl", "sidebar", schluessel, params.faellig_von ?? "", params.faellig_bis ?? ""],
    queryFn: () => vorgaengeApi.list({ ...params, limit: String(ZAEHL_LIMIT) }),
    enabled,
    staleTime: 60 * 1000,
  });
  return {
    anzahl: data?.filter((v) => !ERLEDIGTE_STATUS.includes(v.status)).length,
    gekappt: (data?.length ?? 0) >= ZAEHL_LIMIT,
  };
}

function SchnellfilterKachel({
  icon: Icon,
  label,
  anzahl,
  gekappt = false,
  warnung = false,
  onClick,
}: {
  icon: typeof CalendarDays;
  label: string;
  anzahl: number | undefined;
  gekappt?: boolean;
  /** Zahl > 0 als Status-Rot (nur "Dringend"); 0 bleibt gedaempft. */
  warnung?: boolean;
  onClick: () => void;
}) {
  const zahlKlasse = !anzahl ? "text-label2" : warnung ? "text-st-fehlt" : "text-label";
  return (
    <button
      type="button"
      onClick={onClick}
      className="card-ap flex flex-col items-start gap-2 p-2.5 text-left transition-opacity hover:opacity-90"
    >
      <div className="flex w-full items-start justify-between">
        <Icon size={15} strokeWidth={2} className="text-label2" aria-hidden="true" />
        <span className={`text-zeile font-bold tabular-nums ${zahlKlasse}`}>
          {anzahl === undefined ? "–" : gekappt ? `${ZAEHL_LIMIT}+` : anzahl}
        </span>
      </div>
      <span className="text-sekundaer font-semibold text-label2">{label}</span>
    </button>
  );
}

export function OfficeLayout() {
  const { currentUser, hatRecht, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const fehlerbericht = useFehlerbericht();
  const { outboxCount, isOnline } = useAppLiveDaten();
  const vorgemerkteAnzahl = useVorgemerkteZeitenAnzahl();
  // In localStorage gemerkt (nicht im Backend wie office_nav_items) -- ist
  // reine Anzeige-Praeferenz des Geraets, keine Nutzer-Stammdaten.
  const [eingeklappt, setEingeklappt] = useState(() => localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1");
  // Pro Kategorie merken, ob sie eingeklappt ist -- ebenfalls reine
  // Geraete-Anzeige-Praeferenz, kein Backend-Feld (analog SIDEBAR_STORAGE_KEY).
  const [eingeklappteKategorien, setEingeklappteKategorien] = useState<Record<string, boolean>>(
    geladeneEingeklappteKategorien,
  );

  const [workspaceKey, setWorkspaceKey] = useState<string | null>(() => {
    try {
      return localStorage.getItem(WORKSPACE_STORAGE_KEY);
    } catch {
      return null;
    }
  });

  const sidebarUmschalten = () => {
    setEingeklappt((prev) => {
      const naechster = !prev;
      localStorage.setItem(SIDEBAR_STORAGE_KEY, naechster ? "1" : "0");
      return naechster;
    });
  };

  const kategorieUmschalten = (name: string) => {
    setEingeklappteKategorien((prev) => {
      const naechster = { ...prev, [name]: !prev[name] };
      localStorage.setItem(KATEGORIEN_STORAGE_KEY, JSON.stringify(naechster));
      return naechster;
    });
  };

  const sichtbar = fuerOffice(sichtbareNavSeiten(currentUser, hatRecht));
  // null = keine Auswahl gespeichert -> unveraendertes Verhalten (alles zeigen)
  const eigeneAuswahl = currentUser?.office_nav_items?.items;
  const angezeigt = eigeneAuswahl
    ? sichtbar.filter((seite) => eigeneAuswahl.includes(seite.key))
    : sichtbar;
  // Eigene Menue-Kategorien des Mandanten (siehe pages/NavKategorienPage.tsx)
  // -- leer/undefined faellt in effektiveNavGruppen auf die vier
  // Standardkategorien zurueck, komplett ohne Sonderfall hier.
  const { data: customKategorien } = useQuery({
    queryKey: ["nav-kategorien"],
    queryFn: () => navKategorienApi.get(),
    staleTime: 5 * 60 * 1000,
  });
  // Workspace-Filter greift vor den Menue-Kategorien; nicht verfuegbarer oder
  // nie gewaehlter Workspace -> erster verfuegbarer.
  const workspaces = verfuegbareWorkspaces(angezeigt);
  // Aktiver Eintrag und Workspace folgen der Route (Reload, Deep-Link); der
  // gemerkte Workspace gilt nur, wo die Route nichts vorgibt.
  const aktiverKey = aktiverNavKey(pathname, angezeigt);
  const aktiveSeite = angezeigt.find((seite) => seite.key === aktiverKey);
  const aktiverWorkspace = workspaceFuerRoute(aktiveSeite, workspaces, workspaceKey);
  useEffect(() => {
    document.title = aktiveSeite ? `${aktiveSeite.label} – FieldVibe` : "FieldVibe";
  }, [aktiveSeite]);
  const imWorkspace = aktiverWorkspace
    ? angezeigt.filter((seite) => seiteInWorkspace(seite, aktiverWorkspace))
    : angezeigt;
  const gruppen = effektiveNavGruppen(imWorkspace, customKategorien);

  const workspaceWechseln = (key: WorkspaceKey) => {
    const ziel = workspaces.find((w) => w.key === key);
    if (!ziel) return;
    setWorkspaceKey(key);
    try {
      localStorage.setItem(WORKSPACE_STORAGE_KEY, key);
    } catch {
      // Merken ist nur Komfort.
    }
    const route = workspaceStartRoute(ziel, angezeigt);
    if (route) navigate(route);
  };

  const { data: projekte } = useQuery({ queryKey: ["projekte"], queryFn: () => projekteApi.list(), enabled: hatRecht("projekte", "sehen") });
  const aktiveProjekte = (projekte ?? []).filter((p) => !p.archiviert).slice(0, 6);

  // "Alle" kommt aus dem Kennzahlen-Endpoint (exakt, nur mit Statistik-Recht),
  // sonst wie die anderen Kacheln aus der Listen-Route.
  const darfVorgaenge = hatRecht("vorgaenge", "sehen");
  const darfStatistik = hatRecht("statistik", "sehen");
  const { data: kennzahlen } = useQuery({
    queryKey: ["vorgang-kennzahlen", "sidebar"],
    queryFn: () => statistikApi.vorgangKennzahlen(),
    enabled: darfStatistik,
  });
  const heute = useOffeneAnzahl("heute", { faellig_von: heuteIso(), faellig_bis: heuteIso() }, darfVorgaenge);
  const woche = useOffeneAnzahl("woche", { faellig_von: heuteIso(), faellig_bis: heuteIso(7) }, darfVorgaenge);
  const dringend = useOffeneAnzahl("dringend", { faellig_bis: heuteIso() }, darfVorgaenge);
  const alleListe = useOffeneAnzahl("alle", {}, darfVorgaenge && !darfStatistik);

  const zurMobilenAnsicht = () => {
    const ziel = mobileUrl();
    if (!ziel) return;
    // Ohne dieses Abschalten wuerde die Geraete-Weiche den Nutzer auf einem
    // breiten Bildschirm sofort wieder hierher zurueckholen.
    weicheAus();
    window.location.href = ziel;
  };

  // Die früheren Hilfslinks am Fuß der Seitenleiste plus Abmelden -- selten
  // gebraucht, deshalb gebündelt statt dauerhaft sichtbar.
  const nutzerMenue: (AktionsMenueEintrag | "trenner")[] = [
    { label: "Seitenleiste anpassen", icon: Settings, onClick: () => navigate("/einstellungen/seitenleiste") },
    ...(currentUser?.role === "mandant_admin"
      ? [{ label: "Menü-Kategorien", icon: FolderCog, onClick: () => navigate("/einstellungen/kategorien") }]
      : []),
    "trenner",
    ...(hatRecht("fehlerberichte", "sehen")
      ? [{ label: "Fehler & Ideen", icon: ClipboardList, onClick: () => navigate("/fehlerberichte") }]
      : []),
    ...(fehlerbericht.verfuegbar
      ? [
          { label: "Fehler melden", icon: Bug, onClick: () => fehlerbericht.aufnehmen() },
          { label: "Idee einreichen", icon: Lightbulb, onClick: () => fehlerbericht.aufnehmen({ art: "idee" }) },
        ]
      : []),
    "trenner",
    { label: "Zur mobilen Ansicht", icon: Smartphone, onClick: zurMobilenAnsicht },
    { label: "Abmelden", icon: LogOut, onClick: logout, destruktiv: true },
  ];

  // "/" und Strg/Cmd+K öffnen die Suche -- "/" nur außerhalb von Eingabefeldern
  useEffect(() => {
    const beiTaste = (e: KeyboardEvent) => {
      const ziel = e.target as HTMLElement | null;
      const tippt = ziel?.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(ziel?.tagName ?? "");
      const strgK = e.key === "k" && (e.ctrlKey || e.metaKey);
      const schraeg = e.key === "/" && !tippt && !e.ctrlKey && !e.metaKey && !e.altKey;
      if (!strgK && !schraeg) return;
      e.preventDefault();
      navigate("/suche");
    };
    document.addEventListener("keydown", beiTaste);
    return () => document.removeEventListener("keydown", beiTaste);
  }, [navigate]);

  return (
    <div className="office-flaechen min-h-screen bg-gbg text-label" style={{ "--klebe-abstand": "0.75rem" } as CSSProperties}>
      <ImpersonationBanner />
      {!isOnline && (
        <div className="bg-st-arbeit-bg px-4 py-1.5 text-center text-sekundaer font-medium text-st-arbeit">
          Offline – Änderungen werden gespeichert und später synchronisiert
        </div>
      )}

      <div className="flex">
        <aside
          className={`sticky top-0 flex h-screen shrink-0 flex-col overflow-hidden border-r-[0.5px] border-sepstrong py-3.5 transition-[width] duration-200 ease-in-out ${
            eingeklappt ? "w-16 px-2" : "w-64 px-2.5"
          }`}
          style={{ backgroundColor: "var(--side)", backdropFilter: "blur(30px)", WebkitBackdropFilter: "blur(30px)" }}
        >
          <div className={`mb-3 flex items-center ${eingeklappt ? "flex-col gap-2" : "justify-between px-1.5"}`}>
            <div className="flex min-w-0 items-center gap-2.5">
              {eingeklappt ? (
                <Logo variante="pin" hoehe={28} />
              ) : (
                <button onClick={() => navigate("/vorgaenge")} className="min-w-0 text-left" aria-label="FieldVibe – zu den Vorgängen">
                  <Logo variante="wortmarke" hoehe={23} />
                </button>
              )}
            </div>
            <button
              onClick={sidebarUmschalten}
              aria-label={eingeklappt ? "Seitenleiste ausklappen" : "Seitenleiste einklappen"}
              title={eingeklappt ? "Ausklappen" : "Einklappen"}
              className="btn-ap-toolbar shrink-0"
            >
              {eingeklappt ? <PanelLeftOpen size={16} strokeWidth={2} /> : <PanelLeftClose size={16} strokeWidth={2} />}
            </button>
          </div>

          {workspaces.length > 1 && (
            <div
              role="tablist"
              aria-label="Workspace"
              className={`mb-3 flex gap-1 ${eingeklappt ? "flex-col" : "flex-wrap"}`}
            >
              {workspaces.map((w) => {
                const aktiv = w.key === aktiverWorkspace?.key;
                return (
                  <button
                    key={w.key}
                    role="tab"
                    aria-selected={aktiv}
                    title={eingeklappt ? w.label : undefined}
                    onClick={() => workspaceWechseln(w.key)}
                    className={`flex h-[28px] items-center justify-center rounded-[7px] text-sekundaer font-medium ${
                      eingeklappt ? "px-0" : "gap-1.5 px-2.5"
                    } ${aktiv ? "bg-fill2 text-label" : "text-label2 hover:bg-fill hover:text-label"}`}
                  >
                    <w.icon size={14} strokeWidth={2} className={aktiv ? "text-tint" : ""} />
                    {!eingeklappt && w.label}
                  </button>
                );
              })}
            </div>
          )}

          {!eingeklappt && aktiverWorkspace?.key === "operativ" && darfVorgaenge && (
            <div className="mb-4 grid grid-cols-2 gap-2">
              <SchnellfilterKachel
                icon={CalendarDays}
                label="Heute"
                anzahl={heute.anzahl}
                gekappt={heute.gekappt}
                onClick={() => navigate(`/vorgaenge?faellig_von=${heuteIso()}&faellig_bis=${heuteIso()}`)}
              />
              <SchnellfilterKachel
                icon={Clock}
                label="Diese Woche"
                anzahl={woche.anzahl}
                gekappt={woche.gekappt}
                onClick={() => navigate(`/vorgaenge?faellig_von=${heuteIso()}&faellig_bis=${heuteIso(7)}`)}
              />
              <SchnellfilterKachel
                icon={Flag}
                label="Dringend"
                anzahl={dringend.anzahl}
                gekappt={dringend.gekappt}
                warnung
                onClick={() => navigate(`/vorgaenge?faellig_bis=${heuteIso()}`)}
              />
              <SchnellfilterKachel
                icon={Inbox}
                label="Alle"
                anzahl={darfStatistik ? kennzahlen?.offene_vorgaenge_gesamt : alleListe.anzahl}
                gekappt={!darfStatistik && alleListe.gekappt}
                onClick={() => navigate("/vorgaenge")}
              />
            </div>
          )}

          <nav aria-label="Hauptnavigation" className="flex-1 space-y-4 overflow-x-hidden overflow-y-auto">
            {gruppen.map((gruppe) => {
              const kollabiert = !!eingeklappteKategorien[gruppe.name];
              return (
                <div key={gruppe.name}>
                  {eingeklappt ? (
                    <div className="mx-1 mb-1.5 border-t-[0.5px] border-sep" />
                  ) : (
                    <button
                      onClick={() => kategorieUmschalten(gruppe.name)}
                      aria-expanded={!kollabiert}
                      className="flex w-full items-center justify-between px-2 pb-1.5 text-meta font-semibold text-label2 uppercase hover:text-label"
                    >
                      <span>{gruppe.name}</span>
                      <ChevronDown
                        size={12}
                        strokeWidth={2}
                        className={`transition-transform duration-150 ${kollabiert ? "-rotate-90" : ""}`}
                      />
                    </button>
                  )}
                  {!kollabiert &&
                    gruppe.seiten.map((seite) => (
                      <Link
                        key={seite.key}
                        to={seite.route}
                        aria-current={seite.key === aktiverKey ? "page" : undefined}
                        title={eingeklappt ? seite.label : undefined}
                        className={`relative mb-0.5 flex h-[30px] items-center rounded-[7px] text-sekundaer ${
                          eingeklappt ? "justify-center px-0" : "gap-2.5 px-2.5"
                        } ${seite.key === aktiverKey ? "bg-fill2 font-semibold text-label" : "text-label2 hover:bg-fill hover:text-label"}`}
                      >
                        <seite.icon
                          size={17}
                          strokeWidth={2}
                          className={`shrink-0 ${seite.key === aktiverKey ? "text-tint" : "text-label2"}`}
                        />
                        {!eingeklappt && <span className="truncate">{seite.label}</span>}
                        {seite.key === "zeiten_buchen" && !!vorgemerkteAnzahl && (
                          <span
                            className={
                              eingeklappt
                                ? "absolute right-0.5 top-0.5 h-2 w-2 rounded-full bg-st-fehlt-dot"
                                : "ml-auto flex h-4 min-w-[16px] shrink-0 items-center justify-center rounded-full bg-st-fehlt-dot px-1 text-meta font-bold text-white"
                            }
                          >
                            {!eingeklappt && (vorgemerkteAnzahl > 9 ? "9+" : vorgemerkteAnzahl)}
                          </span>
                        )}
                      </Link>
                    ))}
                </div>
              );
            })}

            {!eingeklappt && aktiveProjekte.length > 0 && (
              <div>
                <p className="px-2 pb-1.5 text-meta font-semibold text-label2 uppercase">Aktive Projekte</p>
                {aktiveProjekte.map((p) => (
                  <NavLink
                    key={p.id}
                    to={`/vorgaenge?projekt_id=${p.id}`}
                    className="mb-0.5 flex h-[30px] items-center gap-2.5 rounded-[7px] px-2.5 text-sekundaer text-label2 hover:bg-fill hover:text-label"
                  >
                    <Folder size={15} strokeWidth={2} className="shrink-0 text-label2" aria-hidden="true" />
                    <span className="truncate">{p.name}</span>
                  </NavLink>
                ))}
              </div>
            )}
          </nav>

          <div className="border-t-[0.5px] border-sep pt-2.5">
            <AktionsMenue
              label="Benutzermenü"
              eintraege={nutzerMenue}
              richtung="oben"
              ausloeser={({ offen }) => (
                <span
                  className={`flex w-full items-center gap-2.5 rounded-[7px] py-1 text-left hover:bg-fill ${
                    eingeklappt ? "justify-center px-0" : "px-1.5"
                  } ${offen ? "bg-fill" : ""}`}
                >
                  <Monogramm name={currentUser?.name ?? "?"} groesse={28} />
                  {!eingeklappt && (
                    <>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sekundaer font-semibold text-label">{currentUser?.name}</span>
                        <span className="block truncate text-meta text-label2">
                          {currentUser?.account_typ_name ?? (currentUser ? ROLLE_LABEL[currentUser.role] : "")}
                        </span>
                      </span>
                      <ChevronUp size={14} strokeWidth={2} className="shrink-0 text-label2" />
                    </>
                  )}
                </span>
              )}
            />
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <header
            className="sticky top-0 z-30 flex items-center justify-end gap-2 border-b-[0.5px] border-sepstrong px-5 py-2.5"
            style={{ backgroundColor: "var(--win)" }}
          >
            {outboxCount > 0 && (
              <span
                title={`${outboxCount} noch nicht synchronisiert`}
                className="flex items-center gap-1 rounded-[var(--radius-ap-pill)] bg-st-arbeit-bg px-2 py-1 text-sekundaer font-medium text-st-arbeit"
              >
                <Clock size={13} strokeWidth={2} /> {outboxCount}
              </span>
            )}
            <button
              onClick={() => navigate("/suche")}
              aria-label="Suche"
              title="Suche (/ oder Strg+K)"
              className="btn-ap-toolbar"
            >
              <Search size={17} strokeWidth={2} />
            </button>
            <ThemeToggle />
          </header>

          <main className="px-5 py-5">
            <SeitenGrenze />
          </main>
        </div>
      </div>
    </div>
  );
}
