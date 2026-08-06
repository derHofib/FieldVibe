import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { ThemeToggle } from "./ThemeToggle";

const NAV_ITEMS = [
  { to: "/mandanten", label: "Mandanten", icon: "🏢" },
  { to: "/accounts", label: "Accounts", icon: "👥" },
  { to: "/audit-log", label: "Audit-Log", icon: "📋" },
  { to: "/update", label: "Update", icon: "⬆️" },
];

export function Layout() {
  const { currentUser, logout } = useAuth();

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
                  `btn-touch flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${
                    isActive
                      ? "bg-slate-900 text-white dark:bg-cyan-600"
                      : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                  }`
                }
              >
                <span aria-hidden>{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <div className="flex flex-1 flex-col">
          <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3 dark:border-slate-800 dark:bg-slate-900">
            <span className="text-sm text-slate-600 dark:text-slate-300">
              Angemeldet als <strong>{currentUser?.name}</strong> ({currentUser?.role})
            </span>
            <div className="flex items-center gap-1">
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
