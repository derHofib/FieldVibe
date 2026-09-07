import { useQuery } from "@tanstack/react-query";
import { Mail, Plus, Settings } from "lucide-react";
import { useState } from "react";

import { mailApi } from "../../api/endpoints";
import { SeitenKopf } from "../OfficeUi";
import { MailClient } from "./MailClient";
import { MailKontoFormular } from "./MailKontoFormular";

type Ansicht = { art: "client" } | { art: "konto-neu" } | { art: "konto-bearbeiten" };

/** Orchestriert das Postfach: kein Konto -> Einrichtungsformular, sonst der
 * Drei-Spalten-Mailclient fuer das aktive Konto. Mehrere Postfaecher werden
 * nicht gemischt angezeigt (ein Ordnerbaum pro Konto ist eindeutiger als ein
 * gemeinsamer Posteingang mit rätselhafter Herkunft je Nachricht) -- ein
 * Umschalter oben wechselt zwischen ihnen. */
export function OfficePostfachPage() {
  const { data: accounts, isLoading } = useQuery({
    queryKey: ["mail-accounts"],
    queryFn: () => mailApi.accounts.list(),
  });
  const [aktivesKontoId, setAktivesKontoId] = useState<string | null>(null);
  const [ansicht, setAnsicht] = useState<Ansicht>({ art: "client" });

  const aktivesKonto = accounts?.find((a) => a.id === aktivesKontoId) ?? accounts?.[0];

  if (isLoading) {
    return <p className="py-10 text-center text-sm text-ind-ink-3">Lädt…</p>;
  }

  if (!accounts || accounts.length === 0 || ansicht.art === "konto-neu") {
    return (
      <div>
        <SeitenKopf titel="Postfach" />
        <MailKontoFormular
          onFertig={() => setAnsicht({ art: "client" })}
          onAbbrechen={accounts && accounts.length > 0 ? () => setAnsicht({ art: "client" }) : undefined}
        />
      </div>
    );
  }

  if (ansicht.art === "konto-bearbeiten" && aktivesKonto) {
    return (
      <div>
        <SeitenKopf titel="Postfach bearbeiten" />
        <MailKontoFormular
          bestehendesKonto={aktivesKonto}
          onFertig={() => setAnsicht({ art: "client" })}
          onAbbrechen={() => setAnsicht({ art: "client" })}
        />
      </div>
    );
  }

  if (!aktivesKonto) return null;

  return (
    <div>
      <SeitenKopf titel="Postfach">
        {accounts.length > 1 && (
          <select
            value={aktivesKonto.id}
            onChange={(e) => setAktivesKontoId(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-200"
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        )}
        <button
          onClick={() => setAnsicht({ art: "konto-bearbeiten" })}
          title="Postfach-Einstellungen"
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-stone-700 dark:text-stone-400 dark:hover:bg-stone-800"
        >
          <Settings size={15} strokeWidth={2} />
        </button>
        <button
          onClick={() => setAnsicht({ art: "konto-neu" })}
          title="Weiteres Postfach verbinden"
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-stone-700 dark:text-stone-400 dark:hover:bg-stone-800"
        >
          <Plus size={15} strokeWidth={2} />
        </button>
      </SeitenKopf>

      {aktivesKonto.letzter_sync_fehler && (
        <p className="mb-3 flex items-center gap-1.5 rounded-lg bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
          <Mail size={13} strokeWidth={2} /> Letzter Abgleich fehlgeschlagen: {aktivesKonto.letzter_sync_fehler}
        </p>
      )}

      <MailClient account={aktivesKonto} />
    </div>
  );
}
