import { Phone } from "lucide-react";
import type { ReactNode } from "react";

import { telefonHref } from "../../utils/telefonat";
import { useTelefonat, type TelefonatKontext } from "./TelefonatProvider";

/** Telefonnummer als tel:-Link. Der Klick öffnet das Telefon (Handy bzw. Softphone) und zusätzlich das
 * Telefonat-Sheet mit laufender Uhr; ohne Kunden-/Vorgangsbezug bleibt es ein einfacher tel:-Link. */
export function AnrufLink({
  nummer,
  kontext,
  children,
  className = "text-tint-text underline-offset-2 hover:underline",
}: {
  nummer: string;
  kontext?: TelefonatKontext;
  children?: ReactNode;
  className?: string;
}) {
  const { anrufen } = useTelefonat();
  return (
    <a
      href={telefonHref(nummer)}
      onClick={() => kontext && (kontext.kundeId || kontext.vorgangId) && anrufen({ ...kontext, partner: { ...kontext.partner, nummer } })}
      className={className}
    >
      {children ?? nummer}
    </a>
  );
}

/** Runder Anruf-Button (Icon) für Zeilen mit Ansprechpartner. */
export function AnrufButton({ nummer, kontext, name }: { nummer: string; kontext: TelefonatKontext; name: string }) {
  const { anrufen } = useTelefonat();
  return (
    <a
      href={telefonHref(nummer)}
      onClick={() => anrufen({ ...kontext, partner: { ...kontext.partner, nummer } })}
      aria-label={`${name} anrufen`}
      title={`${name} anrufen`}
      className="btn-touch flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-ap-md)] border border-sep text-label hover:bg-fill"
    >
      <Phone size={16} strokeWidth={2} aria-hidden="true" />
    </a>
  );
}
