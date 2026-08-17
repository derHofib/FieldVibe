import { useLayoutEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";

import { notificationsApi } from "../api/endpoints";
import { effektiveLinks, effektiveRotunde, sichtbareNavSeiten, type NavSeite } from "../config/navSeiten";
import { useAuth } from "../context/AuthContext";
import { IconBadge } from "./IconBadge";

// Feste Breite je Rotunde-Platz (siehe Rotunde weiter unten) -- bewusst als
// Konstante statt aus dem DOM gemessen: dadurch laesst sich das gerade
// zentrierte Icon direkt aus scrollLeft berechnen (scrollLeft / Schrittweite),
// ohne Refs pro Icon oder einen IntersectionObserver zu brauchen. Muss zur
// inline gesetzten Breite/dem Gap der Rotunde-Items unten passen.
const ROTUNDE_SLOT_PX = 56;
const ROTUNDE_GAP_PX = 8;
const ROTUNDE_SCHRITT_PX = ROTUNDE_SLOT_PX + ROTUNDE_GAP_PX;

function Badge({ anzahl }: { anzahl: number }) {
  if (anzahl <= 0) return null;
  return (
    <span className="absolute right-0 top-0 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
      {anzahl > 9 ? "9+" : anzahl}
    </span>
  );
}

function FixItem({ seite, badge }: { seite: NavSeite; badge: number }) {
  return (
    <NavLink
      to={seite.route}
      className={({ isActive }) =>
        `btn-touch relative flex shrink-0 flex-col items-center justify-center gap-0.5 px-3 py-1.5 text-[11px] font-medium ${
          isActive ? "text-slate-700 dark:text-stone-200" : "text-slate-400 dark:text-stone-500"
        }`
      }
    >
      {({ isActive }) => (
        <>
          <IconBadge icon={seite.icon} tone={seite.tone} size="sm" active={isActive} />
          {seite.label}
          <Badge anzahl={badge} />
        </>
      )}
    </NavLink>
  );
}

// klein-mittel-gross-mittel-klein statt eines harten Sprungs von "klein" auf
// "unsichtbar": jede Distanzstufe ist nur wenig kleiner/blasser als die
// davor, inklusive einer zusaetzlichen, stark abgeblendeten Ausklingstufe
// (abstand 3) bevor ein Icon ganz verschwindet -- dadurch entsteht beim
// Wischen keine ploetzliche Kante am Rand der sichtbaren Nachbarn.
const ROTUNDE_STUFEN: { massstab: string; deckkraft: string }[] = [
  { massstab: "scale-100", deckkraft: "opacity-100" }, // 0: gross, zentriert
  { massstab: "scale-[0.82]", deckkraft: "opacity-100" }, // 1: mittel
  { massstab: "scale-[0.64]", deckkraft: "opacity-90" }, // 2: klein
  { massstab: "scale-[0.5]", deckkraft: "opacity-35" }, // 3: ausklingend
];
const ROTUNDE_STUFE_UNSICHTBAR = { massstab: "scale-[0.5]", deckkraft: "opacity-0" };

// Ein Rotunde-Platz: das gerade zentrierte Icon (abstand === 0) erscheint in
// derselben Groesse wie die festen Icons links vom Neu-Button (IconBadge
// "sm" ohne zusaetzliche Skalierung) und traegt als einziges ein Label --
// nach aussen hin werden die Nachbarn stufenweise kleiner/blasser.
function RotundeItem({
  seite,
  abstand,
  badge,
}: {
  seite: NavSeite;
  abstand: number;
  badge: number;
}) {
  const zentriert = abstand === 0;
  const { massstab, deckkraft } = ROTUNDE_STUFEN[abstand] ?? ROTUNDE_STUFE_UNSICHTBAR;

  return (
    <NavLink
      to={seite.route}
      style={{ width: ROTUNDE_SLOT_PX }}
      className={({ isActive }) =>
        `btn-touch relative flex shrink-0 snap-center flex-col items-center justify-center gap-0.5 text-[11px] font-medium transition-all duration-200 ${massstab} ${deckkraft} ${
          isActive ? "text-slate-700 dark:text-stone-200" : "text-slate-400 dark:text-stone-500"
        }`
      }
    >
      {({ isActive }) => (
        <>
          <IconBadge icon={seite.icon} tone={seite.tone} size="sm" active={isActive} />
          {zentriert && seite.label}
          <Badge anzahl={badge} />
        </>
      )}
    </NavLink>
  );
}

function Rotunde({ items, unreadCount }: { items: NavSeite[]; unreadCount: number }) {
  const location = useLocation();
  // Beim ersten Rendern (z.B. frischer Seitenaufruf oder Klick aus einer
  // Push-Benachrichtigung) direkt die gerade aktive Seite mittig zeigen,
  // statt immer bei Position 0 zu starten -- ist die aktive Seite nicht Teil
  // der Rotunde, faellt das auf Position 0 zurueck. Bewusst nur einmalig
  // beim Mounten (useState-Initializer), nicht bei jeder Navigation
  // innerhalb der App neu zentrieren.
  const [startIndex] = useState(() => Math.max(0, items.findIndex((seite) => seite.route === location.pathname)));
  const [zentrumIndex, setZentrumIndex] = useState(startIndex);
  const frameRef = useRef<number | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);
  // Seitliches Polster in Pixeln statt in %: CSS-Prozentpolster wuerde sich
  // auf die Breite der Nav-Pille (des Eltern-Elements) beziehen, nicht auf
  // die tatsaechlich uebrige Breite dieser Rotunde-Zone (die durch die
  // festen Icons links und den Neu-Button schon geschmaelert ist) -- das
  // hatte vorher eine falsch grosse Luecke zum Neu-Button erzeugt. Per JS
  // gemessen, damit auch das erste/letzte Icon exakt bis zur Boxmitte
  // scrollen kann.
  const [seitenPolster, setSeitenPolster] = useState(0);

  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const aktualisieren = () => setSeitenPolster(Math.max(0, (el.clientWidth - ROTUNDE_SLOT_PX) / 2));

    // Erstmessung: Polster direkt am DOM-Element setzen statt nur per
    // setSeitenPolster -- ein State-Update wirkt sich erst nach einem
    // zusaetzlichen Render-Durchlauf im DOM aus. Wuerde die Erstpositionierung
    // (scrollTo unten) vor diesem zweiten Durchlauf laufen, verschiebt sich
    // das Polster danach unter dem bereits gesetzten scrollLeft weg --
    // sichtbar als "falsch zentriertes/abgeschnittenes" Icon beim ersten
    // Rendern. Padding synchron per Style setzen, bevor scrollTo() liest/
    // schreibt (das erzwingt ohnehin ein Layout), vermeidet dieses Wettrennen.
    const startPolster = Math.max(0, (el.clientWidth - ROTUNDE_SLOT_PX) / 2);
    el.style.paddingLeft = `${startPolster}px`;
    el.style.paddingRight = `${startPolster}px`;
    setSeitenPolster(startPolster);
    // scrollLeft = startIndex * Schrittweite zentriert den Startindex exakt
    // unabhaengig von der Polstergroesse (rechnet sich algebraisch heraus).
    // behavior: "instant" verhindert ein sichtbares Reinrutschen beim ersten
    // Rendern, trotz scroll-smooth auf dem Container.
    el.scrollTo({ left: startIndex * ROTUNDE_SCHRITT_PX, behavior: "instant" });

    const beobachter = new ResizeObserver(aktualisieren);
    beobachter.observe(el);
    return () => beobachter.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (items.length === 0) return <div className="min-w-0 flex-1" aria-hidden />;

  const onScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const scrollLeft = event.currentTarget.scrollLeft;
    if (frameRef.current !== undefined) cancelAnimationFrame(frameRef.current);
    frameRef.current = requestAnimationFrame(() => {
      const index = Math.round(scrollLeft / ROTUNDE_SCHRITT_PX);
      setZentrumIndex(Math.max(0, Math.min(items.length - 1, index)));
    });
  };

  return (
    <div
      ref={containerRef}
      className="scrollbar-none flex min-w-0 flex-1 items-center gap-2 overflow-x-auto scroll-smooth snap-x snap-mandatory"
      style={{ paddingLeft: seitenPolster, paddingRight: seitenPolster }}
      onScroll={onScroll}
    >
      {items.map((seite, index) => (
        <RotundeItem
          key={seite.key}
          seite={seite}
          abstand={Math.abs(index - zentrumIndex)}
          badge={seite.key === "meldungen" ? unreadCount : 0}
        />
      ))}
    </div>
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

  // Zwei getrennte Zonen (siehe config/navSeiten.ts + Einstellungen ->
  // "Menüleiste anpassen"): links vom Neu-Button eine feste, nicht wischbare
  // Zone mit genau 2 Seiten, rechts eine wischbare Rotunde beliebiger Laenge.
  // bottom_nav_items === null faellt fuer beide Zonen auf die jeweilige
  // Standardauswahl zurueck.
  const sichtbar = sichtbareNavSeiten(currentUser, hatRecht);
  const sichtbarByKey = new Map(sichtbar.map((seite) => [seite.key, seite]));
  const zuSeiten = (keys: string[]) =>
    keys.map((key) => sichtbarByKey.get(key)).filter((seite): seite is NavSeite => seite !== undefined);

  const linksItems = zuSeiten(effektiveLinks(currentUser?.bottom_nav_items?.links, sichtbar));
  const rotundeItems = zuSeiten(effektiveRotunde(currentUser?.bottom_nav_items?.rotunde, sichtbar));

  return (
    <nav
      className="navbar-soft fixed inset-x-3 bottom-3 z-40 flex items-center gap-1 rounded-full bg-white py-1.5 dark:bg-stone-900"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <div className="flex shrink-0 items-center gap-1">
        {linksItems.map((seite) => (
          <FixItem key={seite.key} seite={seite} badge={seite.key === "meldungen" ? unreadCount : 0} />
        ))}
      </div>

      <NavLink
        to="/neu"
        className="btn-clay -mt-7 flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-linear-to-r from-cyan-500 to-blue-600 text-white ring-4 ring-slate-100 dark:ring-stone-950"
        aria-label="Neuer Vorgang"
      >
        <Plus size={26} strokeWidth={2.5} />
      </NavLink>

      <Rotunde items={rotundeItems} unreadCount={unreadCount} />
    </nav>
  );
}
