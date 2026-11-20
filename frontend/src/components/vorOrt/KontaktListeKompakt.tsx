import { Phone } from "lucide-react";

import { VOR_ORT_ROLLE_LABEL, type PartnerVorOrtKontakt, type PortalVorOrtKontakt } from "../../types";
import { telHref } from "../../utils/vorOrt";

type Eintrag = PortalVorOrtKontakt | PartnerVorOrtKontakt;

function Nummer({ nummer, name }: { nummer: string; name: string }) {
  return (
    <a
      href={telHref(nummer)}
      aria-label={`${name} anrufen: ${nummer}`}
      className="inline-flex items-center gap-1 text-sekundaer font-medium text-tint-text hover:underline"
    >
      <Phone size={13} strokeWidth={2} aria-hidden="true" />
      {nummer}
    </a>
  );
}

/** Nur lesende Kontaktliste für Kunden- und Partnerportal (ohne E-Mail, Telefon als tel:-Link). */
export function KontaktListeKompakt({
  kontakte,
  titel,
  variante = "karte",
}: {
  kontakte: Eintrag[];
  titel: string;
  /** "zelle": Partnerportal (Gruppenkopf steht außen, graue Fläche statt Karte); "inline": Office-Panel, nur Überschrift. */
  variante?: "karte" | "zelle" | "inline";
}) {
  if (kontakte.length === 0) return null;
  return (
    <section aria-label={titel} className={variante === "karte" ? "card-ap p-4" : variante === "zelle" ? "mx-4 rounded-[var(--radius-ap-card)] bg-cell p-4" : ""}>
      {variante === "karte" && <h2 className="mb-2 text-fliess font-semibold text-label2">{titel}</h2>}
      {variante === "inline" && <h3 className="mb-1 text-sekundaer font-semibold text-label2">{titel}</h3>}
      <ul className="divide-y divide-sep">
        {kontakte.map((k, i) => {
          const name = k.name ?? "Ohne Namen";
          const telefon2 = "telefon2" in k ? k.telefon2 : null;
          return (
            <li key={i} className="space-y-0.5 py-2 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-zeile font-medium text-label">{name}</span>
                <span className="rounded-[var(--radius-ap-pill)] bg-fill px-2 py-0.5 text-meta font-medium text-label">
                  {VOR_ORT_ROLLE_LABEL[k.rolle]}
                </span>
                {k.einheit && <span className="text-sekundaer text-label2">{k.einheit}</span>}
              </div>
              {(k.telefon || telefon2) && (
                <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                  {k.telefon && <Nummer nummer={k.telefon} name={name} />}
                  {telefon2 && <Nummer nummer={telefon2} name={name} />}
                </div>
              )}
              {k.erreichbarkeit && <p className="text-sekundaer text-label2">Erreichbar: {k.erreichbarkeit}</p>}
              {k.hinweis && <p className="text-sekundaer text-label2">{k.hinweis}</p>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
