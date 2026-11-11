import { CalendarRange, ClipboardList, User, type LucideIcon } from "lucide-react";
import { NavLink } from "react-router-dom";

import { Logo } from "../components/brand/Logo";
import { ThemeToggle } from "../components/ThemeToggle";
import { usePartnerAuth } from "../context/PartnerAuthContext";
import { RechtlicheLinks } from "../components/RechtlicheLinks";
import { SeitenGrenze } from "../components/ErrorBoundary";

const NAV_ITEMS: { to: string; label: string; icon: LucideIcon }[] = [
  { to: "/partnerportal/auftraege", label: "Aufträge", icon: ClipboardList },
  { to: "/partnerportal/zeitplan", label: "Zeitplan", icon: CalendarRange },
  { to: "/partnerportal/profil", label: "Profil", icon: User },
];

// Mobil: Bottom-Nav (wie Feld-App); ab md: Navigation in der Kopfleiste.
// Kopfleiste zeigt den Betrieb (Logo bzw. Name), der den Partner beauftragt --
// die FieldVibe-Wortmarke steht nur klein im Footer.
export function PartnerPortalLayout() {
  const { currentPartner } = usePartnerAuth();

  return (
    <div className="min-h-screen bg-gbg text-label" style={{ paddingBottom: "calc(61px + env(safe-area-inset-bottom))" }}>
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b-[0.5px] border-sep bg-bar px-4 py-2.5 backdrop-blur-xl">
        {currentPartner?.mandant_logo_url ? (
          <img src={currentPartner.mandant_logo_url} alt={currentPartner.mandant_name} className="h-7 max-w-[140px] object-contain" />
        ) : (
          <span className="max-w-[160px] truncate text-zeile font-bold text-label">
            {currentPartner?.mandant_name ?? <Logo variante="wortmarke" hoehe={22} />}
          </span>
        )}
        <span className="hidden text-sekundaer font-semibold text-label2 sm:inline">Partnerportal</span>
        <nav aria-label="Hauptnavigation" className="ml-4 hidden items-center gap-1 md:flex">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `rounded-[var(--radius-ap-pill)] px-3 py-1.5 text-fliess font-medium ${
                  isActive ? "bg-tintbg text-tint-text" : "text-label2 hover:bg-fill"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex min-w-0 items-center gap-2">
          <span className="truncate text-sekundaer text-label2">{currentPartner?.partner_name}</span>
          <ThemeToggle />
        </div>
      </header>

      <SeitenGrenze />

      <RechtlicheLinks className="pt-2" />

      <footer className="flex items-center justify-center gap-1.5 pt-2 pb-4 text-meta text-label3">
        via <Logo variante="wortmarke" hoehe={12} />
      </footer>

      <nav
        aria-label="Hauptnavigation mobil"
        className="fixed inset-x-0 bottom-0 z-40 flex items-stretch border-t-[0.5px] border-sepstrong bg-bar backdrop-blur-xl md:hidden"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            style={{ height: 49 }}
            className={({ isActive }) =>
              `btn-touch flex flex-1 flex-col items-center justify-center gap-0.5 ${isActive ? "text-tint" : "text-label2"}`
            }
          >
            {({ isActive }) => (
              <>
                <item.icon size={25} strokeWidth={isActive ? 2.2 : 2} aria-hidden="true" />
                <span className={`text-nav font-medium ${isActive ? "text-tint-text" : ""}`}>{item.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
