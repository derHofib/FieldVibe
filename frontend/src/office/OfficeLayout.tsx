import { useQuery } from "@tanstack/react-query";
import {
  CalendarDays,
  ChevronDown,
  Clock,
  Flag,
  FolderCog,
  Inbox,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  Smartphone,
  Zap,
} from "lucide-react";
import type { CSSProperties } from "react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { navKategorienApi, projekteApi, statistikApi } from "../api/endpoints";
import { ImpersonationBanner } from "../components/ImpersonationBanner";
import { Monogramm } from "../components/apple/Monogramm";
import { ThemeToggle } from "../components/ThemeToggle";
import { effektiveNavGruppen, sichtbareNavSeiten } from "../config/navSeiten";
import { useAuth } from "../context/AuthContext";
import { useAppLiveDaten } from "../hooks/useAppLiveDaten";
import { weicheAus } from "./geraeteWeiche";
import { mobileUrl } from "./hostname";

/** Die Seitenleiste wird vollstaendig aus config/navSeiten.ts erzeugt --
 * dieselbe Quelle, aus der die Tab-Bar der Handy-App gespeist wird. Damit
 * kann eine neue Seite nicht in der einen Oberflaeche auftauchen und in der
 * anderen fehlen, und die sichtbar()-Praedikate (Rechte + aktive Module)
 * gelten hier automatisch mit. */
const SIDEBAR_STORAGE_KEY = "fieldvibe-office-sidebar-eingeklappt";
const KATEGORIEN_STORAGE_KEY = "fieldvibe-office-sidebar-kategorien-eingeklappt";

function geladeneEingeklappteKategorien(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(KATEGORIEN_STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

function heuteIso(offsetTage = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetTage);
  return d.toISOString().slice(0, 10);
}

const ROLLE_LABEL: Record<string, string> = {
  super_admin: "Super-Admin",
  mandant_admin: "Administrator",
  loesch_ansicht: "Papierkorb (Ansicht)",
  loesch_operativ: "Papierkorb (Verwaltung)",
};

function SchnellfilterKachel({
  icon: Icon,
  farbeKlasse,
  label,
  anzahl,
  onClick,
}: {
  icon: typeof CalendarDays;
  farbeKlasse: string;
  label: string;
  anzahl?: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="card-ap flex flex-col items-start gap-2 p-2.5 text-left transition-opacity hover:opacity-90"
    >
      <div className="flex w-full items-start justify-between">
        <span className={`flex h-6 w-6 items-center justify-center rounded-full ${farbeKlasse}`}>
          <Icon size={13} strokeWidth={2} className="text-white" />
        </span>
        {anzahl !== undefined && (
          <span className="text-[19px] font-bold tabular-nums text-label">{anzahl}</span>
        )}
      </div>
      <span className="text-xs font-semibold text-label2">{label}</span>
    </button>
  );
}

export function OfficeLayout() {
  const { currentUser, hatRecht, logout } = useAuth();
  const navigate = useNavigate();
  const { outboxCount, isOnline } = useAppLiveDaten();
  // In localStorage gemerkt (nicht im Backend wie office_nav_items) -- ist
  // reine Anzeige-Praeferenz des Geraets, keine Nutzer-Stammdaten.
  const [eingeklappt, setEingeklappt] = useState(() => localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1");
  // Pro Kategorie merken, ob sie eingeklappt ist -- ebenfalls reine
  // Geraete-Anzeige-Praeferenz, kein Backend-Feld (analog SIDEBAR_STORAGE_KEY).
  const [eingeklappteKategorien, setEingeklappteKategorien] = useState<Record<string, boolean>>(
    geladeneEingeklappteKategorien,
  );

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

  const sichtbar = sichtbareNavSeiten(currentUser, hatRecht);
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
  const gruppen = effektiveNavGruppen(angezeigt, customKategorien);

  const { data: projekte } = useQuery({ queryKey: ["projekte"], queryFn: () => projekteApi.list() });
  const aktiveProjekte = (projekte ?? []).filter((p) => !p.archiviert).slice(0, 6);

  // Exakte Zaehlung nur fuer "Alle" (aus dem bereits vorhandenen Kennzahlen-
  // Endpoint) -- fuer Heute/Diese-Woche/Dringend gaebe es das nur durch
  // mehrere zusaetzliche Voll-Feed-Abfragen ohne Backend-Zaehl-Endpoint,
  // siehe docs/ui-redesign/REVIEW.md "Datenluecken".
  const darfStatistik = hatRecht("statistik", "sehen");
  const { data: kennzahlen } = useQuery({
    queryKey: ["vorgang-kennzahlen", "sidebar"],
    queryFn: () => statistikApi.vorgangKennzahlen(),
    enabled: darfStatistik,
  });

  const zurMobilenAnsicht = () => {
    const ziel = mobileUrl();
    if (!ziel) return;
    // Ohne dieses Abschalten wuerde die Geraete-Weiche den Nutzer auf einem
    // breiten Bildschirm sofort wieder hierher zurueckholen.
    weicheAus();
    window.location.href = ziel;
  };

  return (
    <div className="min-h-screen bg-win text-label" style={{ "--klebe-abstand": "0.75rem" } as CSSProperties}>
      <ImpersonationBanner />
      {!isOnline && (
        <div className="bg-st-arbeit-bg px-4 py-1.5 text-center text-xs font-medium text-st-arbeit">
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
              <div className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-[7px] bg-label text-win">
                <Zap size={14} strokeWidth={2} fill="currentColor" />
              </div>
              {!eingeklappt && (
                <button
                  onClick={() => navigate("/vorgaenge")}
                  className="truncate text-left text-sm font-bold text-label"
                >
                  FieldVibe
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

          {!eingeklappt && (
            <div className="mb-4 grid grid-cols-2 gap-2">
              <SchnellfilterKachel
                icon={CalendarDays}
                farbeKlasse="bg-tile-blue"
                label="Heute"
                onClick={() => navigate(`/vorgaenge?faellig_von=${heuteIso()}&faellig_bis=${heuteIso()}`)}
              />
              <SchnellfilterKachel
                icon={Clock}
                farbeKlasse="bg-tile-red"
                label="Diese Woche"
                onClick={() => navigate(`/vorgaenge?faellig_von=${heuteIso()}&faellig_bis=${heuteIso(7)}`)}
              />
              <SchnellfilterKachel
                icon={Flag}
                farbeKlasse="bg-tile-orange"
                label="Dringend"
                onClick={() => navigate(`/vorgaenge?faellig_bis=${heuteIso()}`)}
              />
              <SchnellfilterKachel
                icon={Inbox}
                farbeKlasse="bg-tile-gray"
                label="Alle"
                anzahl={darfStatistik ? kennzahlen?.offene_vorgaenge_gesamt : undefined}
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
                      className="flex w-full items-center justify-between px-2 pb-1.5 text-[11px] font-semibold text-label2 uppercase hover:text-label"
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
                      <NavLink
                        key={seite.key}
                        to={seite.route}
                        title={eingeklappt ? seite.label : undefined}
                        className={({ isActive }) =>
                          `mb-0.5 flex h-[30px] items-center rounded-[7px] text-[13px] ${
                            eingeklappt ? "justify-center px-0" : "gap-2.5 px-2.5"
                          } ${isActive ? "bg-fill2 font-semibold text-label" : "text-label2 hover:bg-fill hover:text-label"}`
                        }
                      >
                        <seite.icon
                          size={17}
                          strokeWidth={2}
                          className={`shrink-0 ${seite.key === "projekte" ? "text-tile-indigo" : "text-tint"}`}
                        />
                        {!eingeklappt && <span className="truncate">{seite.label}</span>}
                      </NavLink>
                    ))}
                </div>
              );
            })}

            {!eingeklappt && aktiveProjekte.length > 0 && (
              <div>
                <p className="px-2 pb-1.5 text-[11px] font-semibold text-label2 uppercase">Aktive Projekte</p>
                {aktiveProjekte.map((p) => (
                  <NavLink
                    key={p.id}
                    to={`/vorgaenge?projekt_id=${p.id}`}
                    className="mb-0.5 flex h-[30px] items-center gap-2.5 rounded-[7px] px-2.5 text-[13px] text-label2 hover:bg-fill hover:text-label"
                  >
                    <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-[3px] bg-tile-indigo">
                      <svg viewBox="0 0 24 24" width={10} height={10} fill="white" aria-hidden="true">
                        <path d="M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6z" />
                      </svg>
                    </span>
                    <span className="truncate">{p.name}</span>
                  </NavLink>
                ))}
              </div>
            )}
          </nav>

          <button
            onClick={() => navigate("/einstellungen/seitenleiste")}
            title={eingeklappt ? "Seitenleiste anpassen" : undefined}
            className={`mt-2 flex h-[30px] items-center rounded-[7px] text-xs font-medium text-label2 hover:bg-fill hover:text-label ${
              eingeklappt ? "justify-center px-0" : "gap-2 px-2.5"
            }`}
          >
            <Settings size={14} strokeWidth={2} className="shrink-0" />
            {!eingeklappt && "Seitenleiste anpassen"}
          </button>
          {currentUser?.role === "mandant_admin" && (
            <button
              onClick={() => navigate("/einstellungen/kategorien")}
              title={eingeklappt ? "Menü-Kategorien" : undefined}
              className={`flex h-[30px] items-center rounded-[7px] text-xs font-medium text-label2 hover:bg-fill hover:text-label ${
                eingeklappt ? "justify-center px-0" : "gap-2 px-2.5"
              }`}
            >
              <FolderCog size={14} strokeWidth={2} className="shrink-0" />
              {!eingeklappt && "Menü-Kategorien"}
            </button>
          )}
          <button
            onClick={zurMobilenAnsicht}
            title={eingeklappt ? "Zur mobilen Ansicht" : undefined}
            className={`mb-2 flex h-[30px] items-center rounded-[7px] text-xs font-medium text-label2 hover:bg-fill hover:text-label ${
              eingeklappt ? "justify-center px-0" : "gap-2 px-2.5"
            }`}
          >
            <Smartphone size={14} strokeWidth={2} className="shrink-0" />
            {!eingeklappt && "Zur mobilen Ansicht"}
          </button>

          <div className={`flex items-center gap-2.5 border-t-[0.5px] border-sep pt-2.5 ${eingeklappt ? "justify-center" : "px-1"}`}>
            <Monogramm name={currentUser?.name ?? "?"} groesse={28} />
            {!eingeklappt && (
              <div className="min-w-0">
                <p className="truncate text-[13px] font-semibold text-label">{currentUser?.name}</p>
                <p className="truncate text-[11px] text-label2">
                  {currentUser?.account_typ_name ?? (currentUser ? ROLLE_LABEL[currentUser.role] : "")}
                </p>
              </div>
            )}
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
                className="flex items-center gap-1 rounded-[var(--radius-ap-pill)] bg-st-arbeit-bg px-2 py-1 text-xs font-medium text-st-arbeit"
              >
                <Clock size={13} strokeWidth={2} /> {outboxCount}
              </span>
            )}
            <span className="text-sm text-label2">{currentUser?.name}</span>
            <button onClick={() => navigate("/suche")} aria-label="Suche" title="Suche" className="btn-ap-toolbar">
              <Search size={17} strokeWidth={2} />
            </button>
            <ThemeToggle />
            <button onClick={logout} aria-label="Abmelden" title="Abmelden" className="btn-ap-toolbar">
              <LogOut size={17} strokeWidth={2} />
            </button>
          </header>

          <main className="px-5 py-5">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
