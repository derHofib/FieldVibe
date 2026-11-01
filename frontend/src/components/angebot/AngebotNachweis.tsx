import { ShieldCheck } from "lucide-react";

import type { Angebot } from "../../types";
import { Hinweiskasten } from "../Hinweiskasten";

const AKTION_LABEL = { annahme: "Annahme", ablehnung: "Ablehnung", widerruf: "Widerruf" } as const;

function zeit(iso: string): string {
  return new Date(iso).toLocaleString("de-DE", { timeZone: "Europe/Berlin", dateStyle: "medium", timeStyle: "short" });
}

/** Widerrufs-Hinweis und Nachweis der letzten Portal-Entscheidung (Office). */
export function AngebotNachweis({ angebot }: { angebot: Angebot }) {
  const nachweis = angebot.letzter_nachweis;
  if (!nachweis && angebot.status !== "widerrufen") return null;
  const geaendert = !!nachweis && !!angebot.fassung_sha256 && nachweis.fassung_sha256 !== angebot.fassung_sha256;

  return (
    <>
      {angebot.status === "widerrufen" && (
        <Hinweiskasten ton="warnung" titel="Vom Kunden widerrufen">
          Der Kunde hat das Angebot{angebot.widerrufen_am ? ` am ${zeit(angebot.widerrufen_am)} Uhr` : ""} über den
          Widerrufsbutton im Portal widerrufen. Bereits angelegte Aufträge wurden nicht automatisch storniert –
          bitte prüfen. Eine Rechnung zu diesem Angebot ist nicht mehr möglich.
        </Hinweiskasten>
      )}
      {nachweis && (
        <section aria-labelledby="angebot-nachweis-titel" className="card-ap space-y-2 p-4">
          <h2 id="angebot-nachweis-titel" className="flex items-center gap-1.5 text-sm font-semibold text-label">
            <ShieldCheck size={15} strokeWidth={2} className="text-tone-emerald" aria-hidden="true" /> Nachweis aus dem
            Kundenportal
          </h2>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
            <dt className="text-label2">Aktion</dt>
            <dd className="text-label">
              {AKTION_LABEL[nachweis.aktion]}
              {nachweis.b2c_flag ? " (Verbraucher-Ablauf)" : ""}
            </dd>
            <dt className="text-label2">Wer</dt>
            <dd className="break-words text-label">
              {nachweis.zugang_name} ({nachweis.zugang_email})
            </dd>
            <dt className="text-label2">Wann</dt>
            <dd className="text-label">{zeit(nachweis.created_at)} Uhr</dd>
            <dt className="text-label2">IP / Gerät</dt>
            <dd className="break-words text-label">
              {nachweis.ip}
              {nachweis.user_agent ? ` · ${nachweis.user_agent}` : ""}
            </dd>
            <dt className="text-label2">Fassung (SHA-256)</dt>
            <dd className="break-all font-mono text-xs text-label">{nachweis.fassung_sha256}</dd>
            {nachweis.belehrung_version && (
              <>
                <dt className="text-label2">Widerrufsbelehrung</dt>
                <dd className="break-words text-label">Version {nachweis.belehrung_version}</dd>
              </>
            )}
          </dl>
          {geaendert && (
            <Hinweiskasten ton="warnung">
              Das Angebot wurde nach dieser Entscheidung verändert: Die aktuelle Fassung stimmt nicht mehr mit der
              Fassung im Nachweis überein.
            </Hinweiskasten>
          )}
        </section>
      )}
    </>
  );
}
