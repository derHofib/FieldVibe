import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { kundenportalAuthApi } from "../../api/endpoints";
import { Starfield } from "../../components/Starfield";

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
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950">
      <Starfield />
      <div className="relative w-full max-w-sm rounded-xl border border-cyan-400/20 bg-slate-900/60 p-8 shadow-[0_0_45px_-10px_rgba(34,211,238,0.25)] backdrop-blur-xl">
        <h1 className="mb-1 text-xl font-bold text-white">Passwort vergessen</h1>
        <p className="mb-6 text-sm text-slate-400">
          Wir senden Ihnen einen Link zum Zurücksetzen, falls die Adresse bekannt ist.
        </p>

        {done ? (
          <p className="rounded-md border border-green-500/30 bg-green-500/10 px-3 py-2 text-sm text-green-300">
            Falls ein Konto mit dieser E-Mail existiert, wurde eine Nachricht mit
            weiteren Schritten verschickt.
          </p>
        ) : (
          <form onSubmit={handleSubmit}>
            <label className="mb-1 block text-sm font-medium text-slate-300">E-Mail</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="btn-touch mb-4 w-full rounded-md border border-slate-700 bg-slate-800/60 px-3 py-2 text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-hidden focus:ring-1 focus:ring-cyan-400/60"
            />
            <button
              type="submit"
              disabled={submitting}
              className="btn-touch w-full rounded-md bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-2 font-medium text-white shadow-[0_0_20px_-5px_rgba(34,211,238,0.6)] hover:from-cyan-400 hover:to-blue-500 disabled:opacity-50"
            >
              {submitting ? "Senden…" : "Link anfordern"}
            </button>
          </form>
        )}

        <Link to="/portal/login" className="mt-4 block text-center text-sm text-slate-400 hover:text-slate-300">
          Zurück zur Anmeldung
        </Link>
      </div>
    </div>
  );
}
