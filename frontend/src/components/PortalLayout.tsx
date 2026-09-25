import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useKundenAuth } from "../context/KundenAuthContext";
import { ThemeToggle } from "./ThemeToggle";

const NAV_ITEMS = [
  { to: "/portal/vorgaenge", label: "Aufträge" },
  { to: "/portal/anfragen", label: "Anfragen" },
  { to: "/portal/angebote", label: "Angebote" },
  { to: "/portal/rechnungen", label: "Rechnungen" },
];

export function PortalLayout() {
  const { currentKunde, logout } = useKundenAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-100 pb-16 dark:bg-stone-950">
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-sep bg-card/80 px-4 py-3 backdrop-blur-md">
        <button
          onClick={() => navigate("/portal/vorgaenge")}
          className="flex items-center gap-1.5 text-lg font-bold text-label"
        >
          Kunden<span className="text-cyan-500 dark:text-cyan-400">portal</span>
        </button>
        <div className="flex items-center gap-2">
          <span className="hidden text-sm text-label sm:inline ">
            {currentKunde?.name}
          </span>
          <ThemeToggle />
          <button
            onClick={logout}
            className="btn-touch rounded-md px-2 text-sm font-medium text-label2 hover:bg-fill"
          >
            Abmelden
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-2xl px-3 py-4">
        <Outlet />
      </main>
      <nav className="fixed bottom-0 left-0 right-0 z-30 flex border-t border-sep bg-card/90 backdrop-blur-md">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `btn-touch flex-1 py-3 text-center text-sm font-medium ${
                isActive
                  ? "text-cyan-600 dark:text-cyan-400"
                  : "text-label2"
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
