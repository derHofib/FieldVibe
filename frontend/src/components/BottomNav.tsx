import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";

import { notificationsApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { istModulAktiv } from "../utils/module";

const items = [
  { to: "/feed", label: "Feed", icon: "📋" },
  { to: "/suche", label: "Suche", icon: "🔍" },
  { to: "/neu", label: "Neu", icon: "➕" },
  { to: "/benachrichtigungen", label: "Meldungen", icon: "🔔" },
  { to: "/profil", label: "Profil", icon: "👤" },
];

const dispoItem = { to: "/dispo", label: "Dispo", icon: "📅" };
const geschaeftItem = { to: "/geschaeft", label: "Geschäft", icon: "💼" };

export function BottomNav() {
  const { currentUser } = useAuth();
  const { data: unread } = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => notificationsApi.list(true),
  });
  const unreadCount = unread?.length ?? 0;

  // Dispo-Board ist Disposition, nicht Kommunikation -- bewusst kein
  // Feed-Ersatz, aber trotzdem ueber die Hauptnavigation erreichbar statt
  // in einem versteckten Menue, da es fuer Disponent/Admin Kernarbeit ist.
  const canDisponieren =
    currentUser?.role === "mandant_admin" || currentUser?.role === "disponent";
  const sichtbareItems = [
    ...items,
    ...(canDisponieren && istModulAktiv(currentUser, "dispo") ? [dispoItem] : []),
    // "Geschäft" buendelt Kunden/Angebote-Rechnungen/Material-Tabs -- ganz
    // weg, wenn alle drei Bereiche fuer diesen Mandanten deaktiviert sind
    // (die Kunde-Basisfunktionen fuers Vorgang-Anlegen bleiben trotzdem
    // ueber die Inline-Anlage in "+Neu" erreichbar, siehe GeschaeftPage).
    ...(canDisponieren && istModulAktiv(currentUser, "kundenverwaltung", "abrechnung", "material")
      ? [geschaeftItem]
      : []),
  ];

  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-slate-200 bg-white/90 backdrop-blur-md dark:border-slate-800 dark:bg-slate-900/80">
      {sichtbareItems.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            `btn-touch relative flex flex-1 flex-col items-center justify-center gap-0.5 py-2 text-xs font-medium ${
              isActive
                ? "text-cyan-600 dark:text-cyan-400"
                : "text-slate-400 dark:text-slate-500"
            }`
          }
        >
          {({ isActive }) => (
            <>
              <span
                className={`text-lg leading-none transition-all ${
                  isActive
                    ? "scale-110 drop-shadow-[0_0_6px_rgba(34,211,238,0.65)]"
                    : "opacity-50 grayscale"
                }`}
              >
                {item.icon}
              </span>
              {item.label}
              {item.to === "/benachrichtigungen" && unreadCount > 0 && (
                <span className="absolute right-4 top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
              )}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
