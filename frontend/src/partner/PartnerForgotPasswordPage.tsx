import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { partnerPortalAuthApi } from "../api/endpoints";
import { ErfolgsHinweis, PartnerAuthShell } from "./PartnerAuthShell";

export function PartnerForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await partnerPortalAuthApi.passwortVergessen(email);
    } catch {
      /* Immer derselbe Hinweis (Enumeration-Schutz), siehe partner_auth.py */
    } finally {
      setSubmitting(false);
      setDone(true);
    }
  }

  return (
    <PartnerAuthShell
      titel="Passwort vergessen"
      untertitel="Wir senden Ihnen einen Link zum Zurücksetzen, falls die Adresse bekannt ist."
    >
      {done ? (
        <ErfolgsHinweis>
          Falls ein Konto mit dieser E-Mail existiert, wurde eine Nachricht mit weiteren Schritten verschickt.
        </ErfolgsHinweis>
      ) : (
        <form onSubmit={handleSubmit}>
          <label htmlFor="partner-forgot-email" className="mb-1 block text-sm font-medium text-label">
            E-Mail
          </label>
          <input
            id="partner-forgot-email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="field-ap btn-touch mb-4"
          />
          <button type="submit" disabled={submitting} className="btn-ap-capsule btn-ap-capsule-primary w-full">
            {submitting ? "Senden…" : "Link anfordern"}
          </button>
        </form>
      )}
      <Link to="/partnerportal/login" className="btn-touch mt-2 flex items-center justify-center text-sm text-tint-text">
        Zurück zur Anmeldung
      </Link>
    </PartnerAuthShell>
  );
}
