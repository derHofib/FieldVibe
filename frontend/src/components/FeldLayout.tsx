import { useQueryClient } from "@tanstack/react-query";
import { Clock, Search, Settings } from "lucide-react";
import { useEffect, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { useEventStream } from "../hooks/useEventStream";
import { useOutboxSync } from "../offline/useOutboxSync";
import { BottomNav } from "./BottomNav";
import { ImpersonationBanner } from "./ImpersonationBanner";
import { ThemeToggle } from "./ThemeToggle";

function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const setTrue = () => setOnline(true);
    const setFalse = () => setOnline(false);
    window.addEventListener("online", setTrue);
    window.addEventListener("offline", setFalse);
    return () => {
      window.removeEventListener("online", setTrue);
      window.removeEventListener("offline", setFalse);
    };
  }, []);
  return online;
}

export function FeldLayout() {
  const { currentUser, logout } = useAuth();
  const kannEinstellungenSehen =
    currentUser?.role === "mandant_admin" || currentUser?.role === "loesch_operativ";
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const outboxCount = useOutboxSync();
  const isOnline = useOnlineStatus();

  useEventStream({
    feed_update: () => {
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      queryClient.invalidateQueries({ queryKey: ["stories"] });
    },
    vorgang_event: (data) => {
      const payload = data as { vorgang_id: string };
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", payload.vorgang_id] });
    },
    notification: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    timer: (data) => {
      const payload = data as { vorgang_id: string };
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung-laufend"] });
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung", payload.vorgang_id] });
    },
  });

  return (
    <div
      className="min-h-screen bg-slate-100 dark:bg-slate-950"
      style={{ paddingBottom: "calc(7.5rem + env(safe-area-inset-bottom))" }}
    >
      <ImpersonationBanner />
      {!isOnline && (
        <div className="bg-slate-800 px-4 py-1.5 text-center text-xs font-medium text-white">
          Offline – Änderungen werden gespeichert und später synchronisiert
        </div>
      )}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200 bg-white/80 px-4 py-3 backdrop-blur-md dark:border-slate-800 dark:bg-slate-900/70">
        <button
          onClick={() => navigate("/feed")}
          className="flex items-center gap-1.5 text-lg font-bold text-slate-800 dark:text-white"
        >
          Field<span className="text-cyan-500 dark:text-cyan-400">Vibe</span>
        </button>
        <div className="flex items-center gap-2">
          {outboxCount > 0 && (
            <span
              title={`${outboxCount} noch nicht synchronisiert`}
              className="flex items-center gap-1 rounded-full bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-800 dark:bg-amber-500/15 dark:text-amber-300"
            >
              <Clock size={13} strokeWidth={2.25} /> {outboxCount}
            </span>
          )}
          <span className="hidden text-sm text-slate-600 sm:inline dark:text-slate-300">
            {currentUser?.name}
          </span>
          <button
            onClick={() => navigate("/suche")}
            aria-label="Suche"
            title="Suche"
            className="btn-touch flex h-9 w-9 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
          >
            <Search size={18} strokeWidth={2} />
          </button>
          <ThemeToggle />
          {kannEinstellungenSehen && (
            <button
              onClick={() => navigate("/einstellungen")}
              aria-label="Einstellungen"
              title="Einstellungen"
              className="btn-touch flex h-9 w-9 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
            >
              <Settings size={18} strokeWidth={2} />
            </button>
          )}
          <button
            onClick={logout}
            className="btn-touch rounded-md px-2 text-sm font-medium text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
          >
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
