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
    <div className="flex min-h-screen items-center justify-center bg-card p-4">
      <Blueprint className="w-full max-w-sm bg-card p-8">
        <h1 className="mb-1 font-heading text-xl font-semibold uppercase tracking-wide text-label">
          Passwort vergessen
        </h1>
        <p className="mb-6 text-sm text-label2">
          Wir senden Ihnen einen Link zum Zurücksetzen, falls die Adresse bekannt ist.
        </p>

        {done ? (
          <p className="border border-st-erledigt px-3 py-2 text-sm text-st-erledigt ">
            Falls ein Konto mit dieser E-Mail existiert, wurde eine Nachricht mit
            weiteren Schritten verschickt.
          </p>
        ) : (
          <form onSubmit={handleSubmit}>
            <label htmlFor="portal-forgot-email" className="mb-1 block text-sm font-medium text-label">
              E-Mail
            </label>
            <input
              id="portal-forgot-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="field-ap btn-touch mb-4"
            />
            <button
              type="submit"
              disabled={submitting}
              className="btn-touch btn-ap-primary w-full py-2 disabled:opacity-50"
            >
              {submitting ? "Senden…" : "Link anfordern"}
            </button>
          </form>
        )}

        <Link to="/portal/login" className="mt-4 block text-center text-sm text-label2 hover:text-label">
          Zurück zur Anmeldung
        </Link>
      </Blueprint>
    </div>
  );
}
