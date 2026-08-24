import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Clock, FolderCog, LogOut, PanelLeftClose, PanelLeftOpen, Search, Settings, Smartphone } from "lucide-react";
import type { CSSProperties } from "react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { navKategorienApi } from "../api/endpoints";
import { ImpersonationBanner } from "../components/ImpersonationBanner";
import { ThemeToggle } from "../components/ThemeToggle";
import { IconBadge } from "../components/IconBadge";
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
    <div
      className="min-h-screen bg-slate-100 dark:bg-stone-950"
      style={{ "--klebe-abstand": "0.75rem" } as CSSProperties}
    >
      <ImpersonationBanner />
      {!isOnline && (
        <div className="bg-slate-800 px-4 py-1.5 text-center text-xs font-medium text-white">
          Offline – Änderungen werden gespeichert und später synchronisiert
        </div>
      )}

      <div className="flex">
        <aside
          className={`sticky top-0 flex h-screen shrink-0 flex-col overflow-hidden border-r border-slate-200 bg-white py-4 transition-[width] duration-200 ease-in-out dark:border-stone-800 dark:bg-stone-900 ${
            eingeklappt ? "w-16 px-2" : "w-56 px-3"
          }`}
        >
          <div className={`mb-5 flex items-center ${eingeklappt ? "justify-center" : "justify-between px-2"}`}>
            {!eingeklappt && (
              <button
                onClick={() => navigate("/vorgaenge")}
                className="truncate text-left text-lg font-bold text-slate-800 dark:text-white"
              >
                Field<span className="text-cyan-500 dark:text-cyan-400">Vibe</span>
              </button>
            )}
            <button
              onClick={sidebarUmschalten}
              aria-label={eingeklappt ? "Seitenleiste ausklappen" : "Seitenleiste einklappen"}
              title={eingeklappt ? "Ausklappen" : "Einklappen"}
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 dark:text-stone-500 dark:hover:bg-stone-800"
            >
              {eingeklappt ? <PanelLeftOpen size={16} strokeWidth={2} /> : <PanelLeftClose size={16} strokeWidth={2} />}
            </button>
          </div>

          <nav className="flex-1 space-y-4 overflow-x-hidden overflow-y-auto">
            {gruppen.map((gruppe) => {
              const kollabiert = !!eingeklappteKategorien[gruppe.name];
              return (
              <div key={gruppe.name}>
                {eingeklappt ? (
                  <div className="mx-1 mb-1.5 border-t border-slate-100 dark:border-stone-800" />
                ) : (
                  <button
                    onClick={() => kategorieUmschalten(gruppe.name)}
                    aria-expanded={!kollabiert}
                    className="flex w-full items-center justify-between rounded-md px-2 pb-1.5 text-[10px] font-bold tracking-wider text-slate-400 uppercase hover:text-slate-600 dark:text-stone-500 dark:hover:text-stone-300"
                  >
                    <span>{gruppe.name}</span>
                    <ChevronDown
                      size={12}
                      strokeWidth={2.5}
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
                      `mb-0.5 flex items-center rounded-lg py-1.5 text-[13px] font-medium ${
                        eingeklappt ? "justify-center px-0" : "gap-2.5 px-2"
                      } ${
                        isActive
                          ? "bg-slate-100 font-semibold text-slate-900 dark:bg-stone-800 dark:text-stone-100"
                          : "text-slate-500 hover:bg-slate-50 dark:text-stone-400 dark:hover:bg-stone-800/60"
                      }`
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <IconBadge icon={seite.icon} tone={seite.tone} size="sm" active={isActive} />
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
            className={`mt-3 flex items-center rounded-lg py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-50 dark:text-stone-500 dark:hover:bg-stone-800/60 ${
              eingeklappt ? "justify-center px-0" : "gap-2 px-2"
            }`}
          >
            <Settings size={14} strokeWidth={2} className="shrink-0" />
            {!eingeklappt && "Seitenleiste anpassen"}
          </button>
          {currentUser?.role === "mandant_admin" && (
            <button
              onClick={() => navigate("/einstellungen/kategorien")}
              title={eingeklappt ? "Menü-Kategorien" : undefined}
              className={`flex items-center rounded-lg py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-50 dark:text-stone-500 dark:hover:bg-stone-800/60 ${
                eingeklappt ? "justify-center px-0" : "gap-2 px-2"
              }`}
            >
              <FolderCog size={14} strokeWidth={2} className="shrink-0" />
              {!eingeklappt && "Menü-Kategorien"}
            </button>
          )}
          <button
            onClick={zurMobilenAnsicht}
            title={eingeklappt ? "Zur mobilen Ansicht" : undefined}
            className={`flex items-center rounded-lg py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-50 dark:text-stone-500 dark:hover:bg-stone-800/60 ${
              eingeklappt ? "justify-center px-0" : "gap-2 px-2"
            }`}
          >
            <Smartphone size={14} strokeWidth={2} className="shrink-0" />
            {!eingeklappt && "Zur mobilen Ansicht"}
          </button>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-30 flex items-center justify-end gap-2 border-b border-slate-200 bg-white/80 px-5 py-2.5 backdrop-blur-md dark:border-stone-800 dark:bg-stone-900/70">
            {outboxCount > 0 && (
              <span
                title={`${outboxCount} noch nicht synchronisiert`}
                className="flex items-center gap-1 rounded-full bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-800 dark:bg-amber-500/15 dark:text-amber-300"
              >
                <Clock size={13} strokeWidth={2.25} /> {outboxCount}
              </span>
            )}
            <span className="text-sm text-slate-600 dark:text-stone-300">{currentUser?.name}</span>
            <button
              onClick={() => navigate("/suche")}
              aria-label="Suche"
              title="Suche"
              className="flex h-9 w-9 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
            >
              <Search size={18} strokeWidth={2} />
            </button>
            <ThemeToggle />
            <button
              onClick={logout}
              aria-label="Abmelden"
              title="Abmelden"
              className="flex h-9 w-9 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
            >
              <LogOut size={18} strokeWidth={2} />
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
