import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useKundenAuth } from "../context/KundenAuthContext";

const NAV_ITEMS = [
  { to: "/portal/vorgaenge", label: "Aufträge" },
  { to: "/portal/angebote", label: "Angebote" },
  { to: "/portal/rechnungen", label: "Rechnungen" },
];

export function PortalLayout() {
  const { currentKunde, logout } = useKundenAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-100 pb-16">
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
        <button onClick={() => navigate("/portal/vorgaenge")} className="text-lg font-bold text-slate-800">
          Kundenportal
        </button>
        <div className="flex items-center gap-3">
          <span className="hidden text-sm text-slate-600 sm:inline">{currentKunde?.name}</span>
          <button
            onClick={logout}
            className="btn-touch rounded-md px-2 text-sm font-medium text-slate-500 hover:bg-slate-100"
          >
            Abmelden
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-2xl px-3 py-4">
        <Outlet />
      </main>
      <nav className="fixed bottom-0 left-0 right-0 z-30 flex border-t border-slate-200 bg-white">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `btn-touch flex-1 py-3 text-center text-sm font-medium ${
                isActive ? "text-slate-900" : "text-slate-400"
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
