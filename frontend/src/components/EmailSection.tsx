import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../api/client";
import type { EmailLog } from "../types";

interface EmailSectionProps {
  queryKey: unknown[];
  listEmails: () => Promise<EmailLog[]>;
  sendEmail: (body: { empfaenger: string; betreff?: string; inhalt?: string }) => Promise<EmailLog>;
  defaultEmpfaenger?: string;
  /** Freitext-Versand (Kunde/Vorgang) braucht Betreff/Inhalt zwingend --
   * beim PDF-Versand (Angebot/Rechnung/Bestellung) sind sie optional, der
   * Server setzt dann einen Standardtext. */
  betreffPflicht?: boolean;
  hinweis?: string;
  /** Verlauf unterhalb des Formulars ausblenden -- fuer Seiten, die die
   * E-Mails bereits an anderer Stelle anzeigen (Vorgang: gemeinsamer
   * Verlauf mit den Kommentaren statt einer zweiten Liste hier). */
  showHistory?: boolean;
  /** Formular direkt offen anzeigen -- fuer den Sprung von der
   * "Nachfragen"-Schnellaktion im Feed (Link mit #email-Hash). */
  defaultOpen?: boolean;
}

/** Wiederverwendbarer "E-Mail senden"-Block mit Compose-Formular und
 * Verlauf darunter -- identisch fuer Kunde/Vorgang (Freitext) und
 * Angebot/Rechnung/Bestellung (PDF-Anhang), nur ueber Props parametriert. */
export function EmailSection({
  queryKey,
  listEmails,
  sendEmail,
  defaultEmpfaenger,
  betreffPflicht = true,
  hinweis,
  showHistory = true,
  defaultOpen = false,
}: EmailSectionProps) {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(defaultOpen);
  const [empfaenger, setEmpfaenger] = useState(defaultEmpfaenger ?? "");
  const [betreff, setBetreff] = useState("");
  const [inhalt, setInhalt] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: emails } = useQuery({ queryKey, queryFn: listEmails });

  const sendMutation = useMutation({
    mutationFn: () =>
      sendEmail({
        empfaenger,
        betreff: betreff || undefined,
        inhalt: inhalt || undefined,
      }),
    onSuccess: (log) => {
      queryClient.invalidateQueries({ queryKey });
      if (log.status === "gesendet") {
        setShowForm(false);
        setBetreff("");
        setInhalt("");
        setError(null);
      } else {
        setError(log.fehlermeldung ?? "Versand fehlgeschlagen");
      }
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Versand fehlgeschlagen"),
  });

  return (
    <div className="border border-ind-line bg-ind-bg p-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ind-ink-3">E-Mail</h2>
        {!showForm && (
          <button
            onClick={() => setShowForm(true)}
            className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
          >
            + E-Mail senden
          </button>
        )}
      </div>

      {showForm && (
        <div className="mb-3 space-y-2 border border-ind-line-2 p-2">
          {hinweis && <p className="text-xs text-ind-ink-3">{hinweis}</p>}
          <div>
            <label className="mb-1 block text-xs font-medium text-ind-ink-3">
              Empfänger
            </label>
            <input
              type="email"
              value={empfaenger}
              onChange={(e) => setEmpfaenger(e.target.value)}
              className="btn-touch w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ind-ink-3">
              Betreff {!betreffPflicht && "(optional)"}
            </label>
            <input
              value={betreff}
              onChange={(e) => setBetreff(e.target.value)}
              className="btn-touch w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ind-ink-3">
              Nachricht {!betreffPflicht && "(optional)"}
            </label>
            <textarea
              value={inhalt}
              onChange={(e) => setInhalt(e.target.value)}
              rows={3}
              className="w-full resize-none border border-ind-line bg-transparent p-2 text-sm text-ind-ink"
            />
          </div>
          {error && <p className="text-xs text-red-700 dark:text-red-400">{error}</p>}
          <div className="flex gap-2">
            <button
              onClick={() => sendMutation.mutate()}
              disabled={
                !empfaenger ||
                (betreffPflicht && (!betreff.trim() || !inhalt.trim())) ||
                sendMutation.isPending
              }
              className="btn-touch flex-1 rounded-md btn-industry btn-industry-primary py-1.5 text-sm font-medium disabled:opacity-50"
            >
              Senden
            </button>
            <button
              onClick={() => {
                setShowForm(false);
                setError(null);
              }}
              className="btn-touch flex-1 rounded-md border border-slate-300 py-1.5 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {showHistory && ((emails ?? []).length === 0 ? (
        <p className="text-sm text-ind-ink-3">Noch keine E-Mails versendet.</p>
      ) : (
        <div className="space-y-1.5">
          {emails!.map((e) => (
            <div key={e.id} className="rounded-md bg-slate-50 p-2 text-sm dark:bg-stone-800/60">
              <div className="flex items-start justify-between gap-2">
                <span className="font-medium text-ind-ink-2">{e.betreff}</span>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                    e.status === "gesendet"
                      ? "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300"
                      : "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300"
                  }`}
                >
                  {e.status === "gesendet" ? "Gesendet" : "Fehler"}
                </span>
              </div>
              <div className="text-xs text-ind-ink-3">
                an {e.empfaenger} ·{" "}
                {new Date(e.created_at).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" })}
                {e.anhang_dateiname && ` · ${e.anhang_dateiname}`}
              </div>
              {e.status === "fehler" && e.fehlermeldung && (
                <p className="mt-0.5 text-xs text-red-600 dark:text-red-400">{e.fehlermeldung}</p>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
