import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";

import { notificationsApi } from "../api/endpoints";

const items = [
  { to: "/feed", label: "Feed", icon: "📋" },
  { to: "/suche", label: "Suche", icon: "🔍" },
  { to: "/neu", label: "Neu", icon: "➕" },
  { to: "/benachrichtigungen", label: "Meldungen", icon: "🔔" },
  { to: "/profil", label: "Profil", icon: "👤" },
];

export function BottomNav() {
  const { data: unread } = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => notificationsApi.list(true),
  });
  const unreadCount = unread?.length ?? 0;

  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-slate-200 bg-white">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            `btn-touch relative flex flex-1 flex-col items-center justify-center gap-0.5 py-2 text-xs font-medium ${
              isActive ? "text-slate-900" : "text-slate-400"
            }`
          }
        >
          <span className="text-lg leading-none">{item.icon}</span>
          {item.label}
          {item.to === "/benachrichtigungen" && unreadCount > 0 && (
            <span className="absolute right-4 top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
