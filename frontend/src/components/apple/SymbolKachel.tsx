import type { LucideIcon } from "lucide-react";

export type KachelFarbe = "blue" | "red" | "green" | "orange" | "indigo" | "gray";

const FARB_KLASSE: Record<KachelFarbe, string> = {
  blue: "bg-tile-blue",
  red: "bg-tile-red",
  green: "bg-tile-green",
  orange: "bg-tile-orange",
  indigo: "bg-tile-indigo",
  gray: "bg-tile-gray",
};

/** Symbol-Kachel (Abschnitt 4.2 + 3.3): 29x29, Radius 7, weißes Symbol,
 * feste Farbe in beiden Modi gleich (Ausnahme von "keine Farbe ausser
 * Status/Herkunft" -- Symbol-Kacheln sind rein illustrativ). */
export function SymbolKachel({
  icon: Icon,
  farbe,
  groesse = 29,
}: {
  icon: LucideIcon;
  farbe: KachelFarbe;
  groesse?: number;
}) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-[7px] ${FARB_KLASSE[farbe]}`}
      style={{ width: groesse, height: groesse }}
      aria-hidden="true"
    >
      <Icon size={Math.round(groesse * 0.57)} strokeWidth={2} className="text-white" />
    </span>
  );
}
