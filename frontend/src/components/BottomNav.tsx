import { useQuery } from "@tanstack/react-query";
import { CalendarDays, ClipboardCheck, Folder, MoreHorizontal, type LucideIcon } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { notificationsApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";

function heuteIso(): string {
  return new Date().toISOString().slice(0, 10);
}

interface Tab {
  key: string;
  label: string;
  icon: LucideIcon;
  route: string;
}

// Abschnitt 5.3: genau 4 feste Tabs, kein wischbarer/individualisierbarer
// Zusatzbereich mehr und kein schwebender Plus-Button (das ist Material
// Design, nicht HIG -- "+" gehoert stattdessen in die Werkzeugleiste der
// jeweiligen Liste). Alles, was vorher ueber die frei waehlbare Rotunde
// erreichbar war, liegt jetzt vollstaendig unter "Mehr" (siehe MehrPage.tsx).
const TABS: Tab[] = [
  { key: "heute", label: "Heute", icon: CalendarDays, route: `/feed?faellig_von=${heuteIso()}&faellig_bis=${heuteIso()}` },
  { key: "auftraege", label: "Aufträge", icon: ClipboardCheck, route: "/feed" },
  { key: "projekte", label: "Projekte", icon: Folder, route: "/projekte" },
  { key: "mehr", label: "Mehr", icon: MoreHorizontal, route: "/mehr" },
];

// "Heute" und "Aufträge" fuehren beide auf /feed (nur mit unterschiedlichem
// Filter in der Suche) -- React-Routers eingebauter NavLink-Abgleich
// vergleicht nur den Pfad, nicht die Suche, deshalb hier von Hand ermittelt,
// welcher der beiden gerade aktiv ist.
function istHeuteFilter(search: string): boolean {
  const params = new URLSearchParams(search);
  const heute = heuteIso();
  return params.get("faellig_von") === heute && params.get("faellig_bis") === heute && !params.get("projekt_id");
}

export function BottomNav() {
  const location = useLocation();
  const { currentUser } = useAuth();
  // loesch_ansicht sieht ausschliesslich den Papierkorb (siehe
  // app/api/routes/papierkorb.py) -- Meldungen wuerden fuer diese Rolle nur
  // mit 403 scheitern, daher gar nicht erst laden.
  const nurPapierkorb = currentUser?.role === "loesch_ansicht";
  const { data: unread } = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => notificationsApi.list(true),
    enabled: !nurPapierkorb,
  });
  // "Meldungen" ist jetzt ein Eintrag im "Mehr"-Tab statt eines eigenen
  // fixen Slots -- der ungelesen-Zaehler wandert deshalb als Sammel-Badge
  // auf das "Mehr"-Symbol selbst (verbreitetes iOS-Muster fuer einen
  // "Mehr"-Tab, der mehrere Unterseiten buendelt).
  const unreadCount = unread?.length ?? 0;
  const aufFeed = location.pathname === "/feed";
  const heuteAktiv = aufFeed && istHeuteFilter(location.search);
  const aktivByKey: Record<string, boolean> = {
    heute: heuteAktiv,
    auftraege: aufFeed && !heuteAktiv,
    projekte: location.pathname.startsWith("/projekte"),
    mehr: location.pathname === "/mehr",
  };

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 flex items-stretch border-t-[0.5px] border-sepstrong bg-bar backdrop-blur-xl"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      {TABS.map((tab) => {
        const isActive = aktivByKey[tab.key];
        return (
          <Link
            key={tab.key}
            to={tab.route}
            aria-current={isActive ? "page" : undefined}
            className={`btn-touch flex flex-1 flex-col items-center justify-center gap-0.5 ${
              isActive ? "text-tint" : "text-label2"
            }`}
            style={{ height: 49 }}
          >
            <span className="relative">
              <tab.icon size={25} strokeWidth={isActive ? 2.2 : 2} aria-hidden="true" />
              {tab.key === "mehr" && unreadCount > 0 && (
                <span className="absolute -right-2 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-st-fehlt-dot px-1 text-[10px] font-bold text-white">
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
              )}
            </span>
            <span className="text-[10px] font-medium">{tab.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
