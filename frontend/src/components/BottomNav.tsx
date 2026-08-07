import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  Bell,
  Briefcase,
  CalendarDays,
  EllipsisVertical,
  Inbox,
  type LucideIcon,
  Plus,
  Rss,
  Trash2,
  User,
} from "lucide-react";
import { useState } from "react";
import { NavLink } from "react-router-dom";

import { notificationsApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { IconBadge, type IconTone } from "./IconBadge";
import { istModulAktiv } from "../utils/module";

function NavItem({ to, label, icon, tone }: { to: string; label: string; icon: LucideIcon; tone: IconTone }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `btn-touch flex flex-1 flex-col items-center justify-center gap-0.5 py-1.5 text-[11px] font-medium ${
          isActive ? "text-slate-700 dark:text-slate-200" : "text-slate-400 dark:text-slate-500"
        }`
      }
    >
      {({ isActive }) => (
        <>
          <IconBadge icon={icon} tone={tone} size="sm" active={isActive} />
          {label}
        </>
      )}
    </NavLink>
  );
}

const dispoItem = { to: "/dispo", label: "Dispo", icon: CalendarDays, tone: "amber" as const };
const geschaeftItem = { to: "/geschaeft", label: "Geschäft", icon: Briefcase, tone: "emerald" as const };
const rechnungseingangItem = {
  to: "/rechnungseingang",
  label: "Rechnungseingang",
  icon: Inbox,
  tone: "cyan" as const,
};
const auswertungItem = { to: "/auswertung", label: "Auswertung", icon: BarChart3, tone: "indigo" as const };
const meldungenItem = { to: "/benachrichtigungen", label: "Meldungen", icon: Bell, tone: "rose" as const };
const papierkorbItem = { to: "/papierkorb", label: "Papierkorb", icon: Trash2, tone: "slate" as const };

export function BottomNav() {
  const { currentUser, hatRecht } = useAuth();
  const [mehrOffen, setMehrOffen] = useState(false);
  // loesch_ansicht sieht ausschliesslich den Papierkorb (siehe
  // app/api/routes/papierkorb.py) -- Feed/Meldungen/etc. wuerden fuer diese
  // Rolle nur mit 403 scheitern, daher gar nicht erst laden/anzeigen.
  const nurPapierkorb = currentUser?.role === "loesch_ansicht";
  const istPapierkorbRolle = nurPapierkorb || currentUser?.role === "loesch_operativ";
  const { data: unread } = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => notificationsApi.list(true),
    enabled: !nurPapierkorb,
  });
  const unreadCount = unread?.length ?? 0;

  // Dispo-Board ist Disposition, nicht Kommunikation -- bewusst kein
  // Feed-Ersatz, aber trotzdem ueber die Hauptnavigation erreichbar statt
  // in einem versteckten Menue, da es fuer Account-Typen mit Dispo-Zugriff
  // Kernarbeit ist. mandant_admin/loesch_operativ sehen dieselbe Navigation,
  // da hatRecht() fuer diese Rollen immer true liefert (siehe AuthContext).
  const canDisponieren = hatRecht("dispo", "sehen");

  // Nur die Kernaktionen (Feed, Neu, Profil) bleiben dauerhaft sichtbar --
  // alles andere ist seltener und wandert ins aufklappbare "Mehr"-Menue,
  // damit die Leiste auf schmalen Bildschirmen nicht ueberladen wirkt.
  const mehrItems = [
    ...(nurPapierkorb ? [] : [{ ...meldungenItem, badge: unreadCount }]),
    ...(canDisponieren && istModulAktiv(currentUser, "dispo") ? [{ ...dispoItem, badge: 0 }] : []),
    // "Geschäft" buendelt Kunden/Angebote-Rechnungen/Material-Tabs -- ganz
    // weg, wenn alle drei Bereiche fuer diesen Mandanten deaktiviert sind
    // (die Kunde-Basisfunktionen fuers Vorgang-Anlegen bleiben trotzdem
    // ueber die Inline-Anlage in "+Neu" erreichbar, siehe GeschaeftPage).
    ...(canDisponieren && istModulAktiv(currentUser, "kundenverwaltung", "abrechnung", "material")
      ? [{ ...geschaeftItem, badge: 0 }]
      : []),
    ...(hatRecht("abrechnung", "sehen") && istModulAktiv(currentUser, "abrechnung")
      ? [{ ...rechnungseingangItem, badge: 0 }, { ...auswertungItem, badge: 0 }]
      : []),
    ...(istPapierkorbRolle ? [{ ...papierkorbItem, badge: 0 }] : []),
  ];
  const mehrBadge = mehrItems.reduce((sum, item) => sum + item.badge, 0);

  return (
    <>
      {mehrOffen && (
        <button
          aria-label="Menü schließen"
          onClick={() => setMehrOffen(false)}
          className="fixed inset-0 z-40 cursor-default"
        />
      )}

      {mehrOffen && (
        <div className="fixed bottom-24 right-3 z-50 w-52 overflow-hidden rounded-2xl bg-white shadow-xl ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
          {mehrItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setMehrOffen(false)}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-4 py-3 text-sm font-medium ${
                  isActive
                    ? "bg-cyan-50 text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-300"
                    : "text-slate-600 dark:text-slate-300"
                }`
              }
            >
              <IconBadge icon={item.icon} tone={item.tone} size="sm" />
              {item.label}
              {item.badge > 0 && (
                <span className="ml-auto flex h-5 min-w-[20px] items-center justify-center rounded-full bg-red-600 px-1 text-[11px] font-bold text-white">
                  {item.badge > 9 ? "9+" : item.badge}
                </span>
              )}
            </NavLink>
          ))}
        </div>
      )}

      <nav
        className="navbar-soft fixed inset-x-3 bottom-3 z-40 flex items-center justify-around rounded-full bg-white py-1.5 dark:bg-slate-900"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <NavItem to="/feed" label="Feed" icon={Rss} tone="sky" />

        <NavLink
          to="/neu"
          className="btn-clay -mt-7 flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-gradient-to-r from-cyan-500 to-blue-600 text-white ring-4 ring-slate-100 dark:ring-slate-950"
          aria-label="Neuer Vorgang"
        >
          <Plus size={26} strokeWidth={2.5} />
        </NavLink>

        <NavItem to="/profil" label="Profil" icon={User} tone="violet" />

        <button
          onClick={() => setMehrOffen((v) => !v)}
          aria-label="Mehr"
          className={`btn-touch relative flex flex-1 flex-col items-center justify-center gap-0.5 py-1.5 text-[11px] font-medium ${
            mehrOffen ? "text-slate-700 dark:text-slate-200" : "text-slate-400 dark:text-slate-500"
          }`}
        >
          <IconBadge icon={EllipsisVertical} tone="slate" size="sm" active={mehrOffen} />
          Mehr
          {mehrBadge > 0 && (
            <span className="absolute right-4 top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
              {mehrBadge > 9 ? "9+" : mehrBadge}
            </span>
          )}
        </button>
      </nav>
    </>
  );
}
