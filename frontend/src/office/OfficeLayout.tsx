import { Clock, LogOut, Search, Smartphone } from "lucide-react";
import type { CSSProperties } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { ImpersonationBanner } from "../components/ImpersonationBanner";
import { ThemeToggle } from "../components/ThemeToggle";
import { IconBadge } from "../components/IconBadge";
import { NAV_KATEGORIE_REIHENFOLGE, sichtbareNavSeiten, type NavKategorie } from "../config/navSeiten";
import { useAuth } from "../context/AuthContext";
import { useAppLiveDaten } from "../hooks/useAppLiveDaten";
import { weicheAus } from "./geraeteWeiche";
import { mobileUrl } from "./hostname";

/** Die Seitenleiste wird vollstaendig aus config/navSeiten.ts erzeugt --
 * dieselbe Quelle, aus der die Bottom-Nav der Handy-App gespeist wird. Damit
 * kann eine neue Seite nicht in der einen Oberflaeche auftauchen und in der
 * anderen fehlen, und die sichtbar()-Praedikate (Rechte + aktive Module)
 * gelten hier automatisch mit. */
export function OfficeLayout() {
  const { currentUser, hatRecht, logout } = useAuth();
  const navigate = useNavigate();
  const { outboxCount, isOnline } = useAppLiveDaten();

  const sichtbar = sichtbareNavSeiten(currentUser, hatRecht);
  const gruppen = NAV_KATEGORIE_REIHENFOLGE.map((kategorie) => ({
    kategorie,
    seiten: sichtbar.filter((seite) => seite.kategorie === kategorie),
  })).filter((gruppe) => gruppe.seiten.length > 0);

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
        <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-slate-200 bg-white px-3 py-4 dark:border-stone-800 dark:bg-stone-900">
          <button
            onClick={() => navigate("/vorgaenge")}
            className="mb-5 px-2 text-left text-lg font-bold text-slate-800 dark:text-white"
          >
            Field<span className="text-cyan-500 dark:text-cyan-400">Vibe</span>
          </button>

          <nav className="flex-1 space-y-4 overflow-y-auto">
            {gruppen.map((gruppe) => (
              <div key={gruppe.kategorie}>
                <p className="px-2 pb-1.5 text-[10px] font-bold tracking-wider text-slate-400 uppercase dark:text-stone-500">
                  {gruppe.kategorie}
                </p>
                {gruppe.seiten.map((seite) => (
                  <NavLink
                    key={seite.key}
                    to={seite.route}
                    className={({ isActive }) =>
                      `mb-0.5 flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-[13px] font-medium ${
                        isActive
                          ? "bg-slate-100 font-semibold text-slate-900 dark:bg-stone-800 dark:text-stone-100"
                          : "text-slate-500 hover:bg-slate-50 dark:text-stone-400 dark:hover:bg-stone-800/60"
                      }`
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <IconBadge icon={seite.icon} tone={seite.tone} size="sm" active={isActive} />
                        {seite.label}
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>

          <button
            onClick={zurMobilenAnsicht}
            className="mt-3 flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-50 dark:text-stone-500 dark:hover:bg-stone-800/60"
          >
            <Smartphone size={14} strokeWidth={2} />
            Zur mobilen Ansicht
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

export type { NavKategorie };
