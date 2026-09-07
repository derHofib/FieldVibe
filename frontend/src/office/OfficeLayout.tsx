import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  Clock,
  FolderCog,
  Hexagon,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  Smartphone,
} from "lucide-react";
import type { CSSProperties } from "react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { navKategorienApi } from "../api/endpoints";
import { ImpersonationBanner } from "../components/ImpersonationBanner";
import { ThemeToggle } from "../components/ThemeToggle";
import { effektiveNavGruppen, sichtbareNavSeiten } from "../config/navSeiten";
import { useAuth } from "../context/AuthContext";
import { useAppLiveDaten } from "../hooks/useAppLiveDaten";
import { weicheAus } from "./geraeteWeiche";
import { mobileUrl } from "./hostname";

/** Die Seitenleiste wird vollstaendig aus config/navSeiten.ts erzeugt --
 * dieselbe Quelle, aus der die Bottom-Nav der Handy-App gespeist wird. Damit
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

  const zurMobilenAnsicht = () => {
    const ziel = mobileUrl();
    if (!ziel) return;
    // Ohne dieses Abschalten wuerde die Geraete-Weiche den Nutzer auf einem
    // breiten Bildschirm sofort wieder hierher zurueckholen.
    weicheAus();
    window.location.href = ziel;
  };

  return (
    <div className="min-h-screen bg-ind-bg text-ind-ink" style={{ "--klebe-abstand": "0.75rem" } as CSSProperties}>
      <ImpersonationBanner />
      {!isOnline && (
        <div className="bg-ind-field px-4 py-1.5 text-center text-xs font-medium text-ind-field-ink">
          Offline – Änderungen werden gespeichert und später synchronisiert
        </div>
      )}

      <div className="flex">
        <aside
          className={`sticky top-0 flex h-screen shrink-0 flex-col overflow-hidden border-r border-ind-line bg-ind-bg py-4 transition-[width] duration-200 ease-in-out ${
            eingeklappt ? "w-16 px-2" : "w-56 px-3"
          }`}
        >
          <div className={`mb-4 flex items-center ${eingeklappt ? "flex-col gap-2" : "justify-between px-1.5"}`}>
            <div className="flex min-w-0 items-center gap-2.5">
              <div className="flex h-[26px] w-[26px] shrink-0 items-center justify-center border border-ind-line-2 text-ind-acc">
                <Hexagon size={15} strokeWidth={1.5} />
              </div>
              {!eingeklappt && (
                <button
                  onClick={() => navigate("/vorgaenge")}
                  className="truncate text-left font-heading text-lg font-semibold uppercase tracking-wide text-ind-ink"
                >
                  Field<span className="text-ind-acc-txt">vibe</span>
                </button>
              )}
            </div>
            <button
              onClick={sidebarUmschalten}
              aria-label={eingeklappt ? "Seitenleiste ausklappen" : "Seitenleiste einklappen"}
              title={eingeklappt ? "Ausklappen" : "Einklappen"}
              className="flex h-7 w-7 shrink-0 items-center justify-center text-ind-ink-3 hover:bg-ind-hover hover:text-ind-ink"
            >
              {eingeklappt ? (
                <PanelLeftOpen size={16} strokeWidth={1.5} />
              ) : (
                <PanelLeftClose size={16} strokeWidth={1.5} />
              )}
            </button>
          </div>

          <nav className="flex-1 space-y-4 overflow-x-hidden overflow-y-auto">
            {gruppen.map((gruppe) => {
              const kollabiert = !!eingeklappteKategorien[gruppe.name];
              return (
              <div key={gruppe.name}>
                {eingeklappt ? (
                  <div className="mx-1 mb-1.5 border-t border-ind-line" />
                ) : (
                  <button
                    onClick={() => kategorieUmschalten(gruppe.name)}
                    aria-expanded={!kollabiert}
                    className="flex w-full items-center justify-between px-2 pb-1.5 text-[10px] font-semibold tracking-[0.14em] text-ind-ink-3 uppercase hover:text-ind-ink"
                  >
                    <span>{gruppe.name}</span>
                    <ChevronDown
                      size={12}
                      strokeWidth={2}
                      className={`transition-transform duration-150 ${kollabiert ? "-rotate-90" : ""}`}
                    />
                  </button>
                )}
                {!kollabiert && gruppe.seiten.map((seite) => (
                  <NavLink
                    key={seite.key}
                    to={seite.route}
                    title={eingeklappt ? seite.label : undefined}
                    className={({ isActive }) =>
                      `relative mb-0.5 flex items-center py-2 text-[13px] font-medium ${
                        eingeklappt ? "justify-center px-0" : "gap-2.5 px-2.5"
                      } ${isActive ? "text-ind-ink" : "text-ind-ink-2 hover:bg-ind-hover hover:text-ind-ink"}`
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <span
                          className="absolute top-1.5 bottom-1.5 left-0 w-0.5 bg-ind-acc"
                          style={{ opacity: isActive ? 1 : 0 }}
                        />
                        <seite.icon size={16} strokeWidth={1.5} className="shrink-0" />
                        {!eingeklappt && <span className="truncate">{seite.label}</span>}
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
              );
            })}
          </nav>

          <button
            onClick={() => navigate("/einstellungen/seitenleiste")}
            title={eingeklappt ? "Seitenleiste anpassen" : undefined}
            className={`mt-3 flex items-center py-1.5 text-xs font-medium text-ind-ink-3 hover:bg-ind-hover hover:text-ind-ink ${
              eingeklappt ? "justify-center px-0" : "gap-2 px-2"
            }`}
          >
            <Settings size={14} strokeWidth={1.5} className="shrink-0" />
            {!eingeklappt && "Seitenleiste anpassen"}
          </button>
          {currentUser?.role === "mandant_admin" && (
            <button
              onClick={() => navigate("/einstellungen/kategorien")}
              title={eingeklappt ? "Menü-Kategorien" : undefined}
              className={`flex items-center py-1.5 text-xs font-medium text-ind-ink-3 hover:bg-ind-hover hover:text-ind-ink ${
                eingeklappt ? "justify-center px-0" : "gap-2 px-2"
              }`}
            >
              <FolderCog size={14} strokeWidth={1.5} className="shrink-0" />
              {!eingeklappt && "Menü-Kategorien"}
            </button>
          )}
          <button
            onClick={zurMobilenAnsicht}
            title={eingeklappt ? "Zur mobilen Ansicht" : undefined}
            className={`flex items-center py-1.5 text-xs font-medium text-ind-ink-3 hover:bg-ind-hover hover:text-ind-ink ${
              eingeklappt ? "justify-center px-0" : "gap-2 px-2"
            }`}
          >
            <Smartphone size={14} strokeWidth={1.5} className="shrink-0" />
            {!eingeklappt && "Zur mobilen Ansicht"}
          </button>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-30 flex items-center justify-end gap-2 border-b border-ind-line bg-ind-bg px-5 py-2.5">
            {outboxCount > 0 && (
              <span
                title={`${outboxCount} noch nicht synchronisiert`}
                className="flex items-center gap-1 border border-ind-warn px-2 py-1 text-xs font-medium text-ind-warn"
              >
                <Clock size={13} strokeWidth={1.5} /> {outboxCount}
              </span>
            )}
            <span className="text-sm text-ind-ink-2">{currentUser?.name}</span>
            <button
              onClick={() => navigate("/suche")}
              aria-label="Suche"
              title="Suche"
              className="btn-industry btn-industry-secondary btn-industry-icon"
            >
              <Search size={18} strokeWidth={1.5} />
            </button>
            <ThemeToggle />
            <button
              onClick={logout}
              aria-label="Abmelden"
              title="Abmelden"
              className="btn-industry btn-industry-secondary btn-industry-icon"
            >
              <LogOut size={18} strokeWidth={1.5} />
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
