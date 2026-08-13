import { useQuery } from "@tanstack/react-query";
import { Plus, type LucideIcon } from "lucide-react";
import { NavLink } from "react-router-dom";

import { notificationsApi } from "../api/endpoints";
import { effektiveNavKeys, sichtbareNavSeiten } from "../config/navSeiten";
import { useAuth } from "../context/AuthContext";
import { IconBadge, type IconTone } from "./IconBadge";

function NavItem({
  to,
  label,
  icon,
  tone,
  badge,
}: {
  to: string;
  label: string;
  icon: LucideIcon;
  tone: IconTone;
  badge?: number;
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `btn-touch relative flex shrink-0 flex-col items-center justify-center gap-0.5 px-3 py-1.5 text-[11px] font-medium ${
          isActive ? "text-slate-700 dark:text-stone-200" : "text-slate-400 dark:text-stone-500"
        }`
      }
    >
      {({ isActive }) => (
        <>
          <IconBadge icon={icon} tone={tone} size="sm" active={isActive} />
          {label}
          {!!badge && badge > 0 && (
            <span className="absolute right-0.5 top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
              {badge > 9 ? "9+" : badge}
            </span>
          )}
        </>
      )}
    </NavLink>
  );
}

export function BottomNav() {
  const { currentUser, hatRecht } = useAuth();
  // loesch_ansicht sieht ausschliesslich den Papierkorb (siehe
  // app/api/routes/papierkorb.py) -- Meldungen wuerden fuer diese Rolle nur
  // mit 403 scheitern, daher gar nicht erst laden.
  const nurPapierkorb = currentUser?.role === "loesch_ansicht";
  const { data: unread } = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => notificationsApi.list(true),
    enabled: !nurPapierkorb,
  });
  const unreadCount = unread?.length ?? 0;

  // Individualisierbare Auswahl (siehe config/navSeiten.ts + Einstellungen ->
  // "Menüleiste anpassen"): Feed und Profil sind Pflichtbestandteile
  // (MANDATORY_KEYS), aber genau wie jede andere Seite Teil derselben
  // wischbaren Liste -- kein optischer Bruch mehr zwischen "fest" und
  // "wählbar". bottom_nav_items === null fällt auf die bisherige
  // "Mehr"-Auswahl zurück, damit sich für bestehende Nutzer ohne eigene
  // Präferenz nichts ändert. Ungültig gewordene oder gerade nicht
  // berechtigte Keys (Rechte/Modul deaktiviert) werden still übersprungen.
  const sichtbar = sichtbareNavSeiten(currentUser, hatRecht);
  const sichtbarByKey = new Map(sichtbar.map((seite) => [seite.key, seite]));
  const items = effektiveNavKeys(currentUser?.bottom_nav_items ?? null, sichtbar)
    .map((key) => sichtbarByKey.get(key))
    .filter((seite): seite is NonNullable<typeof seite> => seite !== undefined);
  // Zwei unabhaengig wischbare Haelften statt einer durchgehenden Leiste:
  // der Neu-Button schwebt fix in der Mitte -- eine durchgehende Leiste
  // wuerde je nach Scroll-Position irgendwann genau darunter einen Eintrag
  // verstecken, mit dieser Aufteilung liegt ueber ihm garantiert immer nur
  // die leere Reserve-Luecke zwischen den beiden Haelften.
  const mitte = Math.ceil(items.length / 2);
  const linkeHaelfte = items.slice(0, mitte);
  const rechteHaelfte = items.slice(mitte);

  const renderItem = (item: (typeof items)[number]) => (
    <NavItem
      key={item.key}
      to={item.route}
      label={item.label}
      icon={item.icon}
      tone={item.tone}
      badge={item.key === "meldungen" ? unreadCount : undefined}
    />
  );

  return (
    <>
      <nav
        className="navbar-soft fixed inset-x-3 bottom-3 z-40 flex items-center overflow-hidden rounded-full bg-white py-1.5 dark:bg-stone-900"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="scrollbar-none flex min-w-0 flex-1 items-center gap-1 overflow-x-auto scroll-smooth">
          {linkeHaelfte.map(renderItem)}
        </div>

        {/* Reservierte Luecke fuer den schwebenden Neu-Button -- bewusst
           kein Nav-Item hier, damit er nie einen Eintrag verdeckt. */}
        <div className="w-14 shrink-0" aria-hidden />

        <div className="scrollbar-none flex min-w-0 flex-1 items-center gap-1 overflow-x-auto scroll-smooth">
          {rechteHaelfte.map(renderItem)}
        </div>
      </nav>

      <NavLink
        to="/neu"
        className="btn-clay fixed bottom-3 left-1/2 z-50 flex h-14 w-14 -translate-x-1/2 -translate-y-7 items-center justify-center rounded-full bg-gradient-to-r from-cyan-500 to-blue-600 text-white ring-4 ring-slate-100 dark:ring-stone-950"
        style={{ marginBottom: "env(safe-area-inset-bottom)" }}
        aria-label="Neuer Vorgang"
      >
        <Plus size={26} strokeWidth={2.5} />
      </NavLink>
    </>
  );
}
