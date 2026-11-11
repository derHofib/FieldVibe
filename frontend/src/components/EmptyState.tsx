import { Lock } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function EmptyState({
  icon: Icon,
  text,
  action,
  className = "",
}: {
  icon: LucideIcon;
  text: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-col items-center gap-2 py-8 text-center ${className}`}>
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-fill text-label2">
        <Icon size={20} strokeWidth={2} aria-hidden="true" />
      </span>
      <p className="max-w-xs text-sekundaer text-label2">{text}</p>
      {action && <div className="mt-2 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

/** Gesperrt-Zustand: Schloss statt Sanduhr/Schild, damit "fehlendes Recht" nicht
 * wie "laedt noch" oder "Fehler" aussieht. `alsH1`: Seiten ohne eigenen SeitenKopf
 * (Office-Guard) brauchen hier den h1, sonst bleibt es ein h2. */
export function GesperrtZustand({
  titel = "Kein Zugriff",
  text,
  action,
  alsH1 = false,
  className = "",
}: {
  titel?: string;
  text: ReactNode;
  action?: ReactNode;
  alsH1?: boolean;
  className?: string;
}) {
  const Titel = alsH1 ? "h1" : "h2";
  return (
    <div className={`mx-auto flex max-w-sm flex-col items-center gap-3 py-12 text-center ${className}`}>
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-fill text-label2">
        <Lock size={20} strokeWidth={2} aria-hidden="true" />
      </span>
      <Titel className="text-zeile font-semibold text-label">{titel}</Titel>
      <p className="text-sekundaer text-label2">{text}</p>
      {action && <div className="mt-2 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}
