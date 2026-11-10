import { ChevronDown, Clock, LogOut, Moon, Search, Settings, Smartphone, Sun } from "lucide-react";
import type { CSSProperties } from "react";
import { useEffect } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

import { ImpersonationBanner } from "../components/ImpersonationBanner";
import { AktionsMenue } from "../components/AktionsMenue";
import { IconBadge } from "../components/IconBadge";
import { NAV_KATEGORIE_REIHENFOLGE, sichtbareNavSeiten, type NavKategorie } from "../config/navSeiten";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { useAppLiveDaten } from "../hooks/useAppLiveDaten";
import { weicheAus } from "./geraeteWeiche";
import { mobileUrl } from "./hostname";
import { aktiverNavKey, fuerOffice, OFFICE_ZUSATZ_KEYS } from "./navAktiv";
import { Tooltip } from "./OfficeUi";

/** Die Seitenleiste wird vollstaendig aus config/navSeiten.ts erzeugt --
 * dieselbe Quelle, aus der die Bottom-Nav der Handy-App gespeist wird. Damit
 * kann eine neue Seite nicht in der einen Oberflaeche auftauchen und in der
 * anderen fehlen, und die sichtbar()-Praedikate (Rechte + aktive Module)
 * gelten hier automatisch mit. */
export function OfficeLayout() {
  const { currentUser, hatRecht, logout } = useAuth();
  const navigate = useNavigate();
  const { outboxCount, isOnline } = useAppLiveDaten();

  const { theme, toggleTheme } = useTheme();
  const { pathname } = useLocation();

  const sichtbar = fuerOffice(sichtbareNavSeiten(currentUser, hatRecht), { currentUser, hatRecht });
  // null = keine Auswahl gespeichert -> unveraendertes Verhalten (alles zeigen)
  const eigeneAuswahl = currentUser?.office_nav_items?.items;
  const angezeigt = eigeneAuswahl
    ? sichtbar.filter(
        (seite) =>
          eigeneAuswahl.includes(seite.key) ||
          // Kunden/Material gehören zur Auswahl-Zeile "Geschäft"
          (OFFICE_ZUSATZ_KEYS.includes(seite.key) && eigeneAuswahl.includes("geschaeft")),
      )
    : sichtbar;
  const gruppen = NAV_KATEGORIE_REIHENFOLGE.map((kategorie) => ({
    kategorie,
    seiten: angezeigt.filter((seite) => seite.kategorie === kategorie),
  })).filter((gruppe) => gruppe.seiten.length > 0);

  // Aus dem Pfad statt aus State, damit Reload und Deep-Links stimmen.
  const aktiverKey = aktiverNavKey(pathname, angezeigt);
  const aktiveSeite = angezeigt.find((seite) => seite.key === aktiverKey);
  useEffect(() => {
    document.title = aktiveSeite ? `${aktiveSeite.label} – FieldVibe` : "FieldVibe";
  }, [aktiveSeite]);

  // "/" und Strg/Cmd+K öffnen die Suche -- "/" nur außerhalb von Eingabefeldern
  useEffect(() => {
    const beiTaste = (e: KeyboardEvent) => {
      const ziel = e.target as HTMLElement | null;
      const tippt =
        ziel?.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(ziel?.tagName ?? "");
      const kuerzel = (e.key === "k" && (e.ctrlKey || e.metaKey)) || (e.key === "/" && !tippt && !e.ctrlKey && !e.metaKey && !e.altKey);
      if (!kuerzel) return;
      e.preventDefault();
      navigate("/suche");
    };
    document.addEventListener("keydown", beiTaste);
    return () => document.removeEventListener("keydown", beiTaste);
  }, [navigate]);

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
      className="office-shell min-h-screen bg-slate-100 dark:bg-stone-950"
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
                {gruppe.seiten.map((seite) => {
                  const isActive = seite.key === aktiverKey;
                  return (
                    <Link
                      key={seite.key}
                      to={seite.route}
                      aria-current={isActive ? "page" : undefined}
                      className={`mb-0.5 flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-[13px] font-medium ${
                        isActive
                          ? "bg-slate-100 font-semibold text-slate-900 dark:bg-stone-800 dark:text-stone-100"
                          : "text-slate-500 hover:bg-slate-50 dark:text-stone-400 dark:hover:bg-stone-800/60"
                      }`}
                    >
                      <IconBadge icon={seite.icon} tone={seite.tone} size="sm" active={isActive} />
                      {seite.label}
                    </Link>
                  );
                })}
              </div>
            ))}
          </nav>

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
            <Tooltip text="Suche (/ oder Strg+K)">
              <button
                onClick={() => navigate("/suche")}
                aria-label="Suche"
                className="flex h-9 w-9 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
              >
                <Search size={18} strokeWidth={2} />
              </button>
            </Tooltip>
            <Tooltip text={theme === "dark" ? "Helles Design" : "Dunkles Design"}>
              <button
                onClick={toggleTheme}
                aria-label={theme === "dark" ? "Helles Design" : "Dunkles Design"}
                className="flex h-9 w-9 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
              >
                {theme === "dark" ? <Sun size={18} strokeWidth={2} /> : <Moon size={18} strokeWidth={2} />}
              </button>
            </Tooltip>
            <AktionsMenue
              label="Benutzermenü"
              eintraege={[
                {
                  label: "Seitenleiste anpassen",
                  icon: Settings,
                  onClick: () => navigate("/einstellungen/seitenleiste"),
                },
                { label: "Zur mobilen Ansicht", icon: Smartphone, onClick: zurMobilenAnsicht },
                "trenner",
                { label: "Abmelden", icon: LogOut, onClick: logout, destruktiv: true },
              ]}
              ausloeser={({ offen }) => (
                <span
                  className={`flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-stone-300 dark:hover:bg-stone-800 ${
                    offen ? "bg-slate-100 dark:bg-stone-800" : ""
                  }`}
                >
                  {currentUser?.name}
                  <ChevronDown size={14} strokeWidth={2} />
                </span>
              )}
            />
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
