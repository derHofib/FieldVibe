import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

const NAV_ITEMS = [
  { to: "/mandanten", label: "Mandanten" },
  { to: "/accounts", label: "Accounts" },
  { to: "/audit-log", label: "Audit-Log" },
];

export function Layout() {
  const { currentUser, logout } = useAuth();

  return (
    <div className="min-h-screen">
      <div className="flex min-h-screen">
        <aside className="w-56 shrink-0 border-r border-slate-200 bg-white p-4">
          <div className="mb-8 text-lg font-bold text-slate-800">FieldVibe</div>
          <nav className="flex flex-col gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `btn-touch flex items-center rounded-md px-3 py-2 text-sm font-medium ${
                    isActive
                      ? "bg-slate-900 text-white"
                      : "text-slate-700 hover:bg-slate-100"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <div className="flex flex-1 flex-col">
          <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
            <span className="text-sm text-slate-600">
              Angemeldet als <strong>{currentUser?.name}</strong> ({currentUser?.role})
            </span>
            <button
              onClick={logout}
              className="btn-touch rounded-md px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              Abmelden
            </button>
          </header>
          <main className="flex-1 p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
