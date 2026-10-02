import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { usePartnerAuth } from "../context/PartnerAuthContext";
import { FehlerHinweis, PartnerAuthShell } from "./PartnerAuthShell";

export function PartnerLoginPage() {
  const { login } = usePartnerAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/partnerportal/auftraege", { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Anmeldung fehlgeschlagen. Bitte Verbindung, E-Mail und Passwort prüfen.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PartnerAuthShell titel="Anmelden" untertitel="Ihre Aufträge und Termine als Partner.">
      <form onSubmit={handleSubmit}>
        {error && <FehlerHinweis>{error}</FehlerHinweis>}

        <label htmlFor="partner-login-email" className="mb-1 block text-sm font-medium text-label">
          E-Mail
        </label>
        <input
          id="partner-login-email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="field-ap btn-touch mb-4"
        />

        <label htmlFor="partner-login-password" className="mb-1 block text-sm font-medium text-label">
          Passwort
        </label>
        <input
          id="partner-login-password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="field-ap btn-touch mb-6"
        />

        <button type="submit" disabled={submitting} className="btn-ap-capsule btn-ap-capsule-primary w-full">
          {submitting ? "Anmelden…" : "Anmelden"}
        </button>

        <Link
          to="/partnerportal/passwort-vergessen"
          className="btn-touch mt-2 flex items-center justify-center text-sm text-tint-text"
        >
          Passwort vergessen?
        </Link>
      </form>
    </PartnerAuthShell>
  );
}
