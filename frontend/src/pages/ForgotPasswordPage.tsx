import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { authApi } from "../api/endpoints";
import Blueprint from "../components/Blueprint";
import { Logo } from "../components/brand/Logo";
import { RechtlicheLinks } from "../components/RechtlicheLinks";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await authApi.passwortVergessen(email);
    } catch {
      /* Immer derselbe Hinweis (Enumeration-Schutz), siehe auth.py */
    } finally {
      setSubmitting(false);
      setDone(true);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-card p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex justify-center">
          <Logo variante="wortmarke" hoehe={32} />
        </div>

        <Blueprint className="bg-card p-8">
          <h1 className="mb-1 text-center font-heading text-sm font-semibold uppercase tracking-[0.14em] text-label2">
            Passwort vergessen
          </h1>
          <p className="mb-6 text-center text-sm text-label2">
            Wir senden dir einen Link zum Zurücksetzen, falls die Adresse bekannt ist.
          </p>

          {done ? (
            <p className="border border-st-erledigt px-3 py-2 text-sm text-st-erledigt">
              Falls ein Konto mit dieser E-Mail existiert, wurde eine Nachricht mit weiteren
              Schritten verschickt.
            </p>
          ) : (
            <form onSubmit={handleSubmit}>
              <label htmlFor="forgot-email" className="mb-1 block text-sm font-medium text-label">
                E-Mail
              </label>
              <input
                id="forgot-email"
                type="email"
                required
                autoComplete="email"
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

          <Link to="/login" className="mt-4 block text-center text-sm text-label2 hover:text-label">
            Zurück zur Anmeldung
          </Link>
        </Blueprint>
        <RechtlicheLinks className="mt-6" />
      </div>
    </div>
  );
}
