import { Clock, Search, Settings } from "lucide-react";
import { Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { useAppLiveDaten } from "../hooks/useAppLiveDaten";
import { BottomNav } from "./BottomNav";
import { ImpersonationBanner } from "./ImpersonationBanner";
import { ThemeToggle } from "./ThemeToggle";

export function FeldLayout() {
  const { currentUser, logout } = useAuth();
  const kannEinstellungenSehen =
    currentUser?.role === "mandant_admin" || currentUser?.role === "loesch_operativ";
  const navigate = useNavigate();
  const { outboxCount, isOnline } = useAppLiveDaten();

  return (
    <div
      className="min-h-screen bg-ind-bg text-ind-ink"
      style={{ paddingBottom: "calc(7.5rem + env(safe-area-inset-bottom))" }}
    >
      <ImpersonationBanner />
      {!isOnline && (
        <div className="bg-ind-field px-4 py-1.5 text-center text-xs font-medium text-ind-field-ink">
          Offline – Änderungen werden gespeichert und später synchronisiert
        </div>
      )}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-ind-line bg-ind-bg px-4 py-3">
        <button
          onClick={() => navigate("/feed")}
          className="flex items-center gap-1.5 font-heading text-lg font-semibold uppercase tracking-wide text-ind-ink"
        >
          Field<span className="text-ind-acc-txt">Vibe</span>
        </button>
        <div className="flex items-center gap-2">
          {outboxCount > 0 && (
            <span
              title={`${outboxCount} noch nicht synchronisiert`}
              className="flex items-center gap-1 border border-ind-warn px-2 py-1 text-xs font-medium text-ind-warn"
            >
              <Clock size={13} strokeWidth={1.5} /> {outboxCount}
            </span>
          )}
          <span className="hidden text-sm text-ind-ink-2 sm:inline">{currentUser?.name}</span>
          <button
            onClick={() => navigate("/suche")}
            aria-label="Suche"
            title="Suche"
            className="btn-touch btn-industry btn-industry-secondary btn-industry-icon"
          >
            <Search size={18} strokeWidth={1.5} />
          </button>
          <ThemeToggle />
          {kannEinstellungenSehen && (
            <button
              onClick={() => navigate("/einstellungen")}
              aria-label="Einstellungen"
              title="Einstellungen"
              className="btn-touch btn-industry btn-industry-secondary btn-industry-icon"
            >
              <Settings size={18} strokeWidth={1.5} />
            </button>
          )}
          <button onClick={logout} className="btn-touch btn-industry btn-industry-ghost">
            Abmelden
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-2xl px-3 py-4">
        <Outlet />
      </main>
      <BottomNav />
    </div>
  );
}
