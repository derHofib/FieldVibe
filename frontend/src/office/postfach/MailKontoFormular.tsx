import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Mail } from "lucide-react";
import { useState } from "react";

import { mailApi } from "../../api/endpoints";
import type { MailAccount, MailVerschluesselung } from "../../types";

const VERSCHLUESSELUNG_OPTIONEN: { wert: MailVerschluesselung; label: string }[] = [
  { wert: "ssl", label: "SSL/TLS" },
  { wert: "starttls", label: "STARTTLS" },
  { wert: "keine", label: "Keine" },
];

interface Props {
  bestehendesKonto?: MailAccount;
  onFertig: () => void;
  onAbbrechen?: () => void;
}

/** Formular fuer "Postfach verbinden" (neues Konto) und Bearbeiten eines
 * bestehenden Kontos. Der "Verbindung testen"-Button ruft denselben
 * Backend-Check auf, den auch das Speichern selbst durchlaeuft -- ein Fehler
 * zeigt sich also schon vor dem eigentlichen Anlegen. */
export function MailKontoFormular({ bestehendesKonto, onFertig, onAbbrechen }: Props) {
  const queryClient = useQueryClient();
  const bearbeiten = !!bestehendesKonto;

  const [name, setName] = useState(bestehendesKonto?.name ?? "");
  const [emailAdresse, setEmailAdresse] = useState(bestehendesKonto?.email_adresse ?? "");
  const [imapHost, setImapHost] = useState(bestehendesKonto?.imap_host ?? "");
  const [imapPort, setImapPort] = useState(bestehendesKonto?.imap_port ?? 993);
  const [imapVerschluesselung, setImapVerschluesselung] = useState<MailVerschluesselung>(
    bestehendesKonto?.imap_verschluesselung ?? "ssl",
  );
  const [imapBenutzername, setImapBenutzername] = useState(
    bestehendesKonto?.imap_benutzername ?? bestehendesKonto?.email_adresse ?? "",
  );
  const [smtpHost, setSmtpHost] = useState(bestehendesKonto?.smtp_host ?? "");
  const [smtpPort, setSmtpPort] = useState(bestehendesKonto?.smtp_port ?? 587);
  const [smtpVerschluesselung, setSmtpVerschluesselung] = useState<MailVerschluesselung>(
    bestehendesKonto?.smtp_verschluesselung ?? "starttls",
  );
  const [smtpBenutzername, setSmtpBenutzername] = useState(
    bestehendesKonto?.smtp_benutzername ?? bestehendesKonto?.email_adresse ?? "",
  );
  const [passwort, setPasswort] = useState("");
  const [signatur, setSignatur] = useState(bestehendesKonto?.signatur ?? "");

  const [testStatus, setTestStatus] = useState<"idle" | "laeuft" | "ok" | "fehler">("idle");
  const [testFehler, setTestFehler] = useState<string | null>(null);
  const [speicherFehler, setSpeicherFehler] = useState<string | null>(null);

  const zugangsdaten = {
    imap_host: imapHost,
    imap_port: imapPort,
    imap_verschluesselung: imapVerschluesselung,
    imap_benutzername: imapBenutzername,
    smtp_host: smtpHost,
    smtp_port: smtpPort,
    smtp_verschluesselung: smtpVerschluesselung,
    smtp_benutzername: smtpBenutzername,
  };

  const testMutation = useMutation({
    mutationFn: () => mailApi.testVerbindung({ ...zugangsdaten, passwort }),
    onMutate: () => {
      setTestStatus("laeuft");
      setTestFehler(null);
    },
    onSuccess: () => setTestStatus("ok"),
    onError: (err: Error) => {
      setTestStatus("fehler");
      setTestFehler(err.message);
    },
  });

  const speichernMutation = useMutation({
    mutationFn: () =>
      bearbeiten
        ? mailApi.accounts.update(bestehendesKonto.id, {
            name,
            email_adresse: emailAdresse,
            ...zugangsdaten,
            ...(passwort ? { passwort } : {}),
            signatur: signatur || null,
          })
        : mailApi.accounts.create({
            name,
            email_adresse: emailAdresse,
            ...zugangsdaten,
            passwort,
            signatur: signatur || null,
          }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mail-accounts"] });
      onFertig();
    },
    onError: (err: Error) => setSpeicherFehler(err.message),
  });

  const passwortPflicht = !bearbeiten;
  const kannSpeichern =
    name.trim() && emailAdresse.trim() && imapHost.trim() && smtpHost.trim() && (passwort || !passwortPflicht);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setSpeicherFehler(null);
        speichernMutation.mutate();
      }}
      className="mx-auto max-w-lg space-y-5"
    >
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal-100 text-teal-600 dark:bg-teal-500/15 dark:text-teal-300">
          <Mail size={18} strokeWidth={2} />
        </span>
        <h1 className="text-lg font-bold text-slate-800 dark:text-white">
          {bearbeiten ? "Postfach bearbeiten" : "Postfach verbinden"}
        </h1>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className="col-span-2 text-xs font-medium text-slate-500 dark:text-stone-400">
          Name (nur für dich sichtbar)
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="z. B. Mein Geschäftspostfach"
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        </label>
        <label className="col-span-2 text-xs font-medium text-slate-500 dark:text-stone-400">
          E-Mail-Adresse
          <input
            type="email"
            value={emailAdresse}
            onChange={(e) => setEmailAdresse(e.target.value)}
            placeholder="technik@meinbetrieb.de"
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        </label>

        <p className="col-span-2 mt-1 text-[11px] font-bold tracking-wider text-slate-400 uppercase dark:text-stone-500">
          Posteingang (IMAP)
        </p>
        <label className="text-xs font-medium text-slate-500 dark:text-stone-400">
          Server
          <input
            value={imapHost}
            onChange={(e) => setImapHost(e.target.value)}
            placeholder="imap.provider.de"
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        </label>
        <label className="text-xs font-medium text-slate-500 dark:text-stone-400">
          Port
          <input
            type="number"
            value={imapPort}
            onChange={(e) => setImapPort(Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        </label>
        <label className="text-xs font-medium text-slate-500 dark:text-stone-400">
          Verschlüsselung
          <select
            value={imapVerschluesselung}
            onChange={(e) => setImapVerschluesselung(e.target.value as MailVerschluesselung)}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          >
            {VERSCHLUESSELUNG_OPTIONEN.map((o) => (
              <option key={o.wert} value={o.wert}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium text-slate-500 dark:text-stone-400">
          Benutzername
          <input
            value={imapBenutzername}
            onChange={(e) => setImapBenutzername(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        </label>

        <p className="col-span-2 mt-1 text-[11px] font-bold tracking-wider text-slate-400 uppercase dark:text-stone-500">
          Postausgang (SMTP)
        </p>
        <label className="text-xs font-medium text-slate-500 dark:text-stone-400">
          Server
          <input
            value={smtpHost}
            onChange={(e) => setSmtpHost(e.target.value)}
            placeholder="smtp.provider.de"
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        </label>
        <label className="text-xs font-medium text-slate-500 dark:text-stone-400">
          Port
          <input
            type="number"
            value={smtpPort}
            onChange={(e) => setSmtpPort(Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        </label>
        <label className="text-xs font-medium text-slate-500 dark:text-stone-400">
          Verschlüsselung
          <select
            value={smtpVerschluesselung}
            onChange={(e) => setSmtpVerschluesselung(e.target.value as MailVerschluesselung)}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          >
            {VERSCHLUESSELUNG_OPTIONEN.map((o) => (
              <option key={o.wert} value={o.wert}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium text-slate-500 dark:text-stone-400">
          Benutzername
          <input
            value={smtpBenutzername}
            onChange={(e) => setSmtpBenutzername(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        </label>

        <label className="col-span-2 text-xs font-medium text-slate-500 dark:text-stone-400">
          Passwort{bearbeiten && " (leer lassen, um es unverändert zu lassen)"}
          <input
            type="password"
            value={passwort}
            onChange={(e) => setPasswort(e.target.value)}
            placeholder={bearbeiten ? "••••••••" : ""}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
          {imapHost.toLowerCase().includes("gmail") || smtpHost.toLowerCase().includes("gmail") ? (
            <span className="mt-1 block text-[11px] text-amber-600 dark:text-amber-400">
              Bei Gmail mit Zwei-Faktor-Anmeldung ein App-Passwort statt des normalen Passworts verwenden.
            </span>
          ) : null}
        </label>

        <label className="col-span-2 text-xs font-medium text-slate-500 dark:text-stone-400">
          Signatur (optional, wird an jede gesendete Mail angehängt)
          <textarea
            value={signatur}
            onChange={(e) => setSignatur(e.target.value)}
            rows={3}
            className="mt-1 w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        </label>
      </div>

      {testStatus === "ok" && (
        <p className="rounded-lg bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300">
          Verbindung erfolgreich.
        </p>
      )}
      {testStatus === "fehler" && (
        <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs font-medium text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
          {testFehler}
        </p>
      )}
      {speicherFehler && (
        <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs font-medium text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
          {speicherFehler}
        </p>
      )}

      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          disabled={!imapHost || !smtpHost || !imapBenutzername || !smtpBenutzername || !passwort || testMutation.isPending}
          onClick={() => testMutation.mutate()}
          className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 disabled:opacity-40 dark:border-stone-700 dark:text-stone-300"
        >
          {testMutation.isPending && <Loader2 size={13} className="animate-spin" />}
          Verbindung testen
        </button>

        <div className="flex items-center gap-2">
          {onAbbrechen && (
            <button
              type="button"
              onClick={onAbbrechen}
              className="rounded-lg px-3 py-2 text-xs font-semibold text-slate-500 dark:text-stone-400"
            >
              Abbrechen
            </button>
          )}
          <button
            type="submit"
            disabled={!kannSpeichern || speichernMutation.isPending}
            className="btn-clay flex items-center gap-1.5 rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-xs font-semibold text-white disabled:opacity-40"
          >
            {speichernMutation.isPending && <Loader2 size={13} className="animate-spin" />}
            {bearbeiten ? "Speichern" : "Postfach anlegen"}
          </button>
        </div>
      </div>
    </form>
  );
}
