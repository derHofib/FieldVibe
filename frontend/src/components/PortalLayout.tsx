import { Link, NavLink, Outlet } from "react-router-dom";

import { useKundenAuth } from "../context/KundenAuthContext";
import { ThemeToggle } from "./ThemeToggle";
import { RechtlicheLinks } from "./RechtlicheLinks";

const NAV_ITEMS = [
  { to: "/portal/vorgaenge", label: "Aufträge" },
  { to: "/portal/anfragen", label: "Anfragen" },
  { to: "/portal/angebote", label: "Angebote" },
  { to: "/portal/rechnungen", label: "Rechnungen" },
];

export function PortalLayout() {
  const { currentKunde, logout } = useKundenAuth();

  return (
    <div className="min-h-screen bg-slate-100 pb-16 dark:bg-stone-950">
      <a
        href="#portal-inhalt"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:text-label"
      >
        Zum Inhalt springen
      </a>
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-sep bg-card/80 px-4 py-3 backdrop-blur-md">
        <Link to="/portal/vorgaenge" className="btn-touch flex items-center text-lg font-bold text-label">
          Kunden<span className="text-tint-text">portal</span>
        </Link>
        <div className="flex items-center gap-2">
          <span className="hidden text-sm text-label sm:inline ">{currentKunde?.name}</span>
          <ThemeToggle />
          <button onClick={logout} className="btn-touch rounded-md px-2 text-sm font-medium text-label2 hover:bg-fill">
            Abmelden
          </button>
        </div>
      </header>
      <main id="portal-inhalt" tabIndex={-1} className="mx-auto max-w-2xl px-3 py-4 outline-none">
        <Outlet />
      </main>
      <footer>
        <RechtlicheLinks className="px-3 pb-4" portalSlug={currentKunde?.portal_slug ?? undefined} barrierefreiheit />
      </footer>
      <nav aria-label="Portal-Navigation" className="fixed bottom-0 left-0 right-0 z-30 flex border-t border-sep bg-card/90 backdrop-blur-md">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `btn-touch flex-1 py-3 text-center text-sm font-medium ${isActive ? "text-tint-text" : "text-label2"}`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
