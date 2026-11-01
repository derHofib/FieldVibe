import { Check } from "lucide-react";

import { STATUS_KREIS_KLASSE, type StatusKey } from "./status";

/** Status-Kreis (Abschnitt 4.2): Neu/Geplant leer, In Arbeit halb gefuellt,
 * Material fehlt mit Punkt in der Mitte, Erledigt gefuellt mit Haken.
 * groesse="mobil" fuer die 22px-Variante in gruppierten Listen, sonst die
 * 16px-Desktop-Variante. */
export function StatusKreis({ status, groesse = "desktop" }: { status: StatusKey; groesse?: "desktop" | "mobil" }) {
  const px = groesse === "mobil" ? 22 : 16;
  const gefuellt = status === "erledigt";

  return (
    <span
      aria-hidden="true"
      className={`relative inline-flex shrink-0 items-center justify-center rounded-full ${STATUS_KREIS_KLASSE[status]}`}
      style={{
        width: px,
        height: px,
        border: "2px solid currentColor",
        background: gefuellt
          ? "currentColor"
          : status === "arbeit"
            ? "linear-gradient(90deg, currentColor 50%, transparent 50%)"
            : "transparent",
      }}
    >
      {gefuellt && <Check size={px - 8} strokeWidth={3} className="text-white" />}
      {status === "fehlt" && (
        <span className="h-[5px] w-[5px] rounded-full bg-current" aria-hidden="true" />
      )}
    </span>
  );
}
