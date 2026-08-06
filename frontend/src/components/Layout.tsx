import { LayoutDashboard, Building2, Users, ScrollText, ShieldCheck, ArrowUpCircle } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { IconBadge, TONE_ROW_ACTIVE, type IconTone } from "./IconBadge";
import { ThemeToggle } from "./ThemeToggle";

const NAV_ITEMS: { to: string; label: string; icon: typeof LayoutDashboard; tone: IconTone }[] = [
  { to: "/uebersicht", label: "Übersicht", icon: LayoutDashboard, tone: "sky" },
  { to: "/mandanten", label: "Mandanten", icon: Building2, tone: "violet" },
  { to: "/accounts", label: "Accounts", icon: Users, tone: "amber" },
  { to: "/audit-log", label: "Audit-Log", icon: ScrollText, tone: "rose" },
  { to: "/dsgvo", label: "DSGVO", icon: ShieldCheck, tone: "emerald" },
  { to: "/update", label: "Update", icon: ArrowUpCircle, tone: "indigo" },
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
    <div className="min-h-screen bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <div className="flex min-h-screen">
        <aside className="w-56 shrink-0 border-r border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <div className="mb-8 flex items-center gap-1.5 text-lg font-bold text-slate-800 dark:text-white">
            Field<span className="text-cyan-500 dark:text-cyan-400">Vibe</span>
          </div>
          <nav className="flex flex-col gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `btn-touch flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? TONE_ROW_ACTIVE[item.tone]
                      : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <IconBadge icon={item.icon} tone={item.tone} size="sm" active={isActive} />
                    {item.label}
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </aside>
        <div className="flex flex-1 flex-col">
          <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3 dark:border-slate-800 dark:bg-slate-900">
            <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">{seitentitel}</span>
            <div className="flex items-center gap-3">
              <span className="text-sm text-slate-600 dark:text-slate-300">
                Angemeldet als <strong>{currentUser?.name}</strong> ({currentUser?.role})
              </span>
              <ThemeToggle />
              <button
                onClick={logout}
                className="btn-touch rounded-md px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
              >
                Abmelden
              </button>
            </div>
          </header>
          <main className="flex-1 p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
