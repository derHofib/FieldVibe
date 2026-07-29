import { useQueryClient } from "@tanstack/react-query";
import { Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { useEventStream } from "../hooks/useEventStream";
import { BottomNav } from "./BottomNav";
import { ImpersonationBanner } from "./ImpersonationBanner";

export function FeldLayout() {
  const { currentUser, logout } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

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
  });

  return (
    <div className="min-h-screen bg-slate-100 pb-16">
      <ImpersonationBanner />
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
        <button
          onClick={() => navigate("/feed")}
          className="text-lg font-bold text-slate-800"
        >
          SocialCRM
        </button>
        <div className="flex items-center gap-3">
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
