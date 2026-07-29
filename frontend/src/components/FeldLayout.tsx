import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { useEventStream } from "../hooks/useEventStream";
import { useOutboxSync } from "../offline/useOutboxSync";
import { BottomNav } from "./BottomNav";
import { ImpersonationBanner } from "./ImpersonationBanner";

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
    <div className="min-h-screen bg-slate-100 pb-16">
      <ImpersonationBanner />
      {!isOnline && (
        <div className="bg-slate-800 px-4 py-1.5 text-center text-xs font-medium text-white">
          Offline – Änderungen werden gespeichert und später synchronisiert
        </div>
      )}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
        <button
          onClick={() => navigate("/feed")}
          className="text-lg font-bold text-slate-800"
        >
          SocialCRM
        </button>
        <div className="flex items-center gap-3">
          {outboxCount > 0 && (
            <span
              title={`${outboxCount} noch nicht synchronisiert`}
              className="flex items-center gap-1 rounded-full bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-800"
            >
              🕘 {outboxCount}
            </span>
          )}
          <span className="hidden text-sm text-slate-600 sm:inline">{currentUser?.name}</span>
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
      <BottomNav />
    </div>
  );
}
