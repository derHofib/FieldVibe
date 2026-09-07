import { LayoutDashboard, Building2, Users, ScrollText, ShieldCheck, ArrowUpCircle, Settings, Hexagon } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { ThemeToggle } from "./ThemeToggle";

const NAV_ITEMS: { to: string; label: string; icon: typeof LayoutDashboard }[] = [
  { to: "/uebersicht", label: "Übersicht", icon: LayoutDashboard },
  { to: "/mandanten", label: "Mandanten", icon: Building2 },
  { to: "/accounts", label: "Accounts", icon: Users },
  { to: "/audit-log", label: "Audit-Log", icon: ScrollText },
  { to: "/dsgvo", label: "DSGVO", icon: ShieldCheck },
  { to: "/update", label: "Update", icon: ArrowUpCircle },
  { to: "/einstellungen", label: "Einstellungen", icon: Settings },
];

function useSeitentitel(): string {
  const { pathname } = useLocation();
  if (pathname.startsWith("/mandanten/")) return "Mandant bearbeiten";
  const treffer = NAV_ITEMS.find((item) => pathname.startsWith(item.to));
  return treffer?.label ?? "";
}

export function Layout() {
  const { currentUser, logout } = useAuth();
  const seitentitel = useSeitentitel();

  return (
    <div className="min-h-screen bg-ind-bg text-ind-ink">
      <div className="flex min-h-screen">
        <aside className="w-16 shrink-0 border-r border-ind-line p-2 sm:w-56 sm:p-4">
          <div className="mb-6 hidden items-center gap-2.5 sm:flex">
            <div className="flex h-[26px] w-[26px] shrink-0 items-center justify-center border border-ind-line-2 text-ind-acc">
              <Hexagon size={15} strokeWidth={1.5} />
            </div>
            <span className="font-heading text-lg font-semibold uppercase tracking-wide text-ind-ink">
              Field<span className="text-ind-acc-txt">Vibe</span>
            </span>
          </div>
          <nav className="flex flex-col gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `btn-touch relative flex items-center justify-center gap-2.5 px-2.5 py-2 text-sm font-medium transition-colors sm:justify-start ${
                    isActive ? "text-ind-ink" : "text-ind-ink-2 hover:bg-ind-hover hover:text-ind-ink"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <span
                      className="absolute top-1.5 bottom-1.5 left-0 hidden w-0.5 bg-ind-acc sm:block"
                      style={{ opacity: isActive ? 1 : 0 }}
                    />
                    <item.icon size={16} strokeWidth={1.5} className="shrink-0" />
                    <span className="hidden sm:inline">{item.label}</span>
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between gap-2 border-b border-ind-line px-3 py-3 sm:px-6">
            <span className="truncate text-sm font-semibold text-ind-ink">{seitentitel}</span>
            <div className="flex items-center gap-3">
              <span className="hidden text-sm text-ind-ink-2 sm:inline">
                Angemeldet als <strong>{currentUser?.name}</strong> ({currentUser?.role})
              </span>
              <ThemeToggle />
              <button onClick={logout} className="btn-touch btn-industry btn-industry-secondary px-3 py-2 text-sm">
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
