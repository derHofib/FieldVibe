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
}: EmailSectionProps) {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
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
    <div className="rounded-lg bg-white p-3 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-500 dark:text-slate-400">E-Mail</h2>
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
        <div className="mb-3 space-y-2 rounded-md bg-slate-50 p-2 dark:bg-slate-800/60">
          {hinweis && <p className="text-xs text-slate-500 dark:text-slate-400">{hinweis}</p>}
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
              Empfänger
            </label>
            <input
              type="email"
              value={empfaenger}
              onChange={(e) => setEmpfaenger(e.target.value)}
              className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
              Betreff {!betreffPflicht && "(optional)"}
            </label>
            <input
              value={betreff}
              onChange={(e) => setBetreff(e.target.value)}
              className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
              Nachricht {!betreffPflicht && "(optional)"}
            </label>
            <textarea
              value={inhalt}
              onChange={(e) => setInhalt(e.target.value)}
              rows={3}
              className="w-full resize-none rounded-md border border-slate-300 p-2 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
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
              className="btn-touch flex-1 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Senden
            </button>
            <button
              onClick={() => {
                setShowForm(false);
                setError(null);
              }}
              className="btn-touch flex-1 rounded-md border border-slate-300 py-1.5 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-300"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {(emails ?? []).length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-slate-500">Noch keine E-Mails versendet.</p>
      ) : (
        <div className="space-y-1.5">
          {emails!.map((e) => (
            <div key={e.id} className="rounded-md bg-slate-50 p-2 text-sm dark:bg-slate-800/60">
              <div className="flex items-start justify-between gap-2">
                <span className="font-medium text-slate-700 dark:text-slate-300">{e.betreff}</span>
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
              <div className="text-xs text-slate-400 dark:text-slate-500">
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
      )}
    </div>
  );
}
