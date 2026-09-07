import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { kundenportalAuthApi } from "../../api/endpoints";
import Blueprint from "../../components/Blueprint";

export function PortalForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await kundenportalAuthApi.passwortVergessen(email);
    } finally {
      // Immer denselben Erfolgs-Hinweis zeigen, egal ob die E-Mail existiert
      // oder der Betrieb ueberhaupt SMTP eingerichtet hat -- der Server
      // antwortet aus demselben Grund immer mit 202 (siehe Backend).
      setSubmitting(false);
      setDone(true);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-ind-bg p-4">
      <Blueprint className="w-full max-w-sm bg-ind-bg p-8">
        <h1 className="mb-1 font-heading text-xl font-semibold uppercase tracking-wide text-ind-ink">
          Passwort vergessen
        </h1>
        <p className="mb-6 text-sm text-ind-ink-3">
          Wir senden Ihnen einen Link zum Zurücksetzen, falls die Adresse bekannt ist.
        </p>

        {done ? (
          <p className="border border-green-500/40 px-3 py-2 text-sm text-green-700 dark:text-green-400">
            Falls ein Konto mit dieser E-Mail existiert, wurde eine Nachricht mit
            weiteren Schritten verschickt.
          </p>
        ) : (
          <form onSubmit={handleSubmit}>
            <label className="mb-1 block text-sm font-medium text-ind-ink-2">E-Mail</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input-industry btn-touch mb-4"
            />
            <button
              type="submit"
              disabled={submitting}
              className="btn-touch btn-industry btn-industry-primary w-full py-2 disabled:opacity-50"
            >
              {submitting ? "Senden…" : "Link anfordern"}
            </button>
          </form>
        )}

        <Link to="/portal/login" className="mt-4 block text-center text-sm text-ind-ink-3 hover:text-ind-ink">
          Zurück zur Anmeldung
        </Link>
      </Blueprint>
    </div>
  );
}
