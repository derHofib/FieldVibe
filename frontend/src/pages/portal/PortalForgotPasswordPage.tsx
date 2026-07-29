import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { kundenportalAuthApi } from "../../api/endpoints";

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
    <div className="flex min-h-screen items-center justify-center bg-slate-100">
      <div className="w-full max-w-sm rounded-lg bg-white p-8 shadow-md">
        <h1 className="mb-1 text-xl font-bold text-slate-800">Passwort vergessen</h1>
        <p className="mb-6 text-sm text-slate-500">
          Wir senden Ihnen einen Link zum Zurücksetzen, falls die Adresse bekannt ist.
        </p>

        {done ? (
          <p className="rounded-md bg-green-50 px-3 py-2 text-sm text-green-700">
            Falls ein Konto mit dieser E-Mail existiert, wurde eine Nachricht mit
            weiteren Schritten verschickt.
          </p>
        ) : (
          <form onSubmit={handleSubmit}>
            <label className="mb-1 block text-sm font-medium text-slate-700">E-Mail</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="btn-touch mb-4 w-full rounded-md border border-slate-300 px-3 py-2"
            />
            <button
              type="submit"
              disabled={submitting}
              className="btn-touch w-full rounded-md bg-slate-900 px-3 py-2 font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {submitting ? "Senden…" : "Link anfordern"}
            </button>
          </form>
        )}

        <Link to="/portal/login" className="mt-4 block text-center text-sm text-slate-500">
          Zurück zur Anmeldung
        </Link>
      </div>
    </div>
  );
}
