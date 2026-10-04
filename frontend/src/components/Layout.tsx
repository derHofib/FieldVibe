import { useQuery } from "@tanstack/react-query";
import { LayoutDashboard, Building2, Users, ScrollText, ShieldCheck, ArrowUpCircle, Settings, Bug } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { fehlerberichteApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { Logo } from "./brand/Logo";
import { ThemeToggle } from "./ThemeToggle";

const NAV_ITEMS: { to: string; label: string; icon: typeof LayoutDashboard }[] = [
  { to: "/uebersicht", label: "Übersicht", icon: LayoutDashboard },
  { to: "/mandanten", label: "Mandanten", icon: Building2 },
  { to: "/accounts", label: "Accounts", icon: Users },
  { to: "/audit-log", label: "Audit-Log", icon: ScrollText },
  { to: "/bugfixes", label: "Bugfixes", icon: Bug },
  { to: "/dsgvo", label: "DSGVO", icon: ShieldCheck },
  { to: "/update", label: "Update", icon: ArrowUpCircle },
  { to: "/einstellungen", label: "Einstellungen", icon: Settings },
];

function useSeitentitel(): string {
  const { pathname } = useLocation();
  if (pathname.startsWith("/mandanten/")) return "Mandant bearbeiten";
  if (pathname.startsWith("/bugfixes/")) return "Fehlerbericht";
  const treffer = NAV_ITEMS.find((item) => pathname.startsWith(item.to));
  return treffer?.label ?? "";
}

export function Layout() {
  const { currentUser, logout } = useAuth();
  const seitentitel = useSeitentitel();
  // Gleicher Query-Key wie die Zaehler-Kacheln der Bugfixes-Seite (ohne Mandantenfilter).
  const { data: zaehler } = useQuery({
    queryKey: ["fehlerberichte", "zaehler", ""],
    queryFn: () => fehlerberichteApi.zaehler(),
    refetchInterval: 60_000,
  });
  const offeneBugfixes = zaehler ? zaehler.neu + zaehler.gesichtet + zaehler.in_arbeit : 0;

  return (
    <div className="min-h-screen bg-card text-label">
      <div className="flex min-h-screen">
        <aside className="w-16 shrink-0 border-r border-sep p-2 sm:w-56 sm:p-4">
          <div className="mb-6 hidden sm:block">
            <Logo variante="wortmarke" hoehe={22} />
          </div>
          <nav className="flex flex-col gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `btn-touch relative flex items-center justify-center gap-2.5 px-2.5 py-2 text-sm font-medium transition-colors sm:justify-start ${
                    isActive ? "text-label" : "text-label hover:bg-fill hover:text-label"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <span
                      className="absolute top-1.5 bottom-1.5 left-0 hidden w-0.5 bg-tint sm:block"
                      style={{ opacity: isActive ? 1 : 0 }}
                    />
                    <item.icon size={16} strokeWidth={1.5} className="shrink-0" />
                    <span className="hidden sm:inline">{item.label}</span>
                    {item.to === "/bugfixes" && offeneBugfixes > 0 && (
                      <span
                        aria-label={`${offeneBugfixes} offene Fehlerberichte`}
                        className="absolute top-0.5 right-0.5 min-w-4 rounded-full bg-tint-solid px-1 text-center text-[10px] leading-4 font-semibold text-white tabular-nums sm:static sm:ml-auto"
                      >
                        {offeneBugfixes}
                      </span>
                    )}
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between gap-2 border-b border-sep px-3 py-3 sm:px-6">
            <h1 className="truncate text-sm font-semibold text-label">{seitentitel}</h1>
            <div className="flex items-center gap-3">
              <span className="hidden text-sm text-label sm:inline">
                Angemeldet als <strong>{currentUser?.name}</strong> ({currentUser?.role})
              </span>
              <ThemeToggle />
              <button onClick={logout} className="btn-touch btn-ap px-3 py-2 text-sm">
                Abmelden
              </button>
            </div>
          </header>
          <main className="flex-1 p-3 sm:p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
