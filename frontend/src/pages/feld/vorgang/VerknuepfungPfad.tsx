import { ChevronRight, ClipboardList, Folder, Lock } from "lucide-react";

import type { Vorgang } from "../../../types";
import { auftragLink, projektLink } from "../../../utils/verknuepfung";

/** Pfad Projekt › Auftrag über der Vorgangsnummer. Eigenständig geführte Vorgänge zeigen statt des
 * Pfads ein Kennzeichen. Ohne Recht liefert der Server bei Eigenständigkeit keine Namen: dann
 * bleibt der Bereich leer, der Vorgang steht für sich. `linksAktiv` nur im Office mit Recht
 * projekte/sehen, sonst reiner grauer Text (Feld-App). */
export function VerknuepfungPfad({
  vorgang,
  linksAktiv,
  navigate,
}: {
  vorgang: Pick<
    Vorgang,
    "projekt_id" | "projekt_name" | "auftrag_id" | "auftrag_titel" | "verknuepfung_eigenstaendig"
  >;
  linksAktiv: boolean;
  navigate: (to: string) => void;
}) {
  const projekt = vorgang.projekt_name ?? null;
  const auftrag = vorgang.auftrag_titel ?? null;
  if (!projekt && !auftrag) return null;

  if (vorgang.verknuepfung_eigenstaendig) {
    return (
      <p className="mb-1 inline-flex items-center gap-1.5 text-sekundaer text-label2">
        <Lock size={13} strokeWidth={1.5} aria-hidden="true" />
        Eigenständig geführt · Rückmeldung an {auftrag ?? projekt} aktiv
      </p>
    );
  }

  const knopf = (text: string, ziel: string) =>
    linksAktiv ? (
      <button type="button" onClick={() => navigate(ziel)} className="min-w-0 truncate text-tint-text underline-offset-2 hover:underline">
        {text}
      </button>
    ) : (
      <span className="min-w-0 truncate">{text}</span>
    );

  return (
    <nav
      aria-label="Zuordnung"
      className={`mb-1 flex min-w-0 flex-wrap items-center gap-x-1.5 text-sekundaer ${linksAktiv ? "" : "text-label2"}`}
    >
      {projekt && (
        <span className="inline-flex min-w-0 items-center gap-1.5">
          <Folder size={13} strokeWidth={1.5} aria-hidden="true" className="shrink-0" />
          {knopf(projekt, projektLink(vorgang.projekt_id ?? ""))}
        </span>
      )}
      {projekt && auftrag && <ChevronRight size={13} strokeWidth={1.5} aria-hidden="true" className="shrink-0 text-label3" />}
      {auftrag && (
        <span className="inline-flex min-w-0 items-center gap-1.5">
          <ClipboardList size={13} strokeWidth={1.5} aria-hidden="true" className="shrink-0" />
          {knopf(auftrag, auftragLink(vorgang.auftrag_id ?? ""))}
        </span>
      )}
    </nav>
  );
}
