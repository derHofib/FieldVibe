import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { partnerPortalAuthApi } from "../api/endpoints";
import { ErfolgsHinweis, FehlerHinweis, PartnerAuthShell } from "./PartnerAuthShell";

export function PartnerResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await partnerPortalAuthApi.passwortZuruecksetzen(token, password);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Zurücksetzen fehlgeschlagen");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PartnerAuthShell titel="Neues Passwort setzen">
      {!token && <FehlerHinweis>Der Link ist unvollständig. Bitte fordern Sie einen neuen an.</FehlerHinweis>}

      {done ? (
        <>
          <ErfolgsHinweis>Passwort erfolgreich geändert. Sie können sich jetzt anmelden.</ErfolgsHinweis>
          <button
            onClick={() => navigate("/partnerportal/login")}
            className="btn-ap-capsule btn-ap-capsule-primary w-full"
          >
            Zur Anmeldung
          </button>
        </>
      ) : (
        <form onSubmit={handleSubmit}>
          {error && <FehlerHinweis>{error}</FehlerHinweis>}
          <label htmlFor="partner-reset-password" className="mb-1 block text-sm font-medium text-label">
            Neues Passwort
          </label>
          <input
            id="partner-reset-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="field-ap btn-touch mb-1"
          />
          <p className="mb-4 text-xs text-label2">Mindestens 10 Zeichen.</p>
          <button
            type="submit"
            disabled={submitting || !token}
            className="btn-ap-capsule btn-ap-capsule-primary w-full"
          >
            {submitting ? "Speichern…" : "Passwort speichern"}
          </button>
        </form>
      )}

      <Link to="/partnerportal/login" className="btn-touch mt-2 flex items-center justify-center text-sm text-tint-text">
        Zurück zur Anmeldung
      </Link>
    </PartnerAuthShell>
  );
}
