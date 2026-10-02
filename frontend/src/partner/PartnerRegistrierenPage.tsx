import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { partnerPortalAuthApi } from "../api/endpoints";
import { usePartnerAuth } from "../context/PartnerAuthContext";
import { FehlerHinweis, PartnerAuthShell } from "./PartnerAuthShell";

/** Abschluss einer Partner-Einladung (Link aus der Einladungsmail,
 * `/partnerportal/registrieren?token=...`, siehe einladung_service.py). */
export function PartnerRegistrierenPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const { loginMitToken } = usePartnerAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const tokens = await partnerPortalAuthApi.registrieren(token, name, password);
      await loginMitToken(tokens);
      navigate("/partnerportal/auftraege", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registrierung fehlgeschlagen");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PartnerAuthShell
      titel="Zugang einrichten"
      untertitel="Mit diesem Zugang sehen Sie Ihre zugewiesenen Aufträge, nehmen sie an und melden den Fortschritt."
    >
      {!token && (
        <FehlerHinweis>Der Link ist unvollständig. Bitte den Einladungslink erneut vom Betrieb anfordern.</FehlerHinweis>
      )}
      <form onSubmit={handleSubmit}>
        {error && <FehlerHinweis>{error}</FehlerHinweis>}

        <label htmlFor="partner-register-name" className="mb-1 block text-sm font-medium text-label">
          Name
        </label>
        <input
          id="partner-register-name"
          autoComplete="name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="field-ap btn-touch mb-4"
        />

        <label htmlFor="partner-register-password" className="mb-1 block text-sm font-medium text-label">
          Passwort
        </label>
        <input
          id="partner-register-password"
          type="password"
          autoComplete="new-password"
          required
          minLength={10}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="field-ap btn-touch mb-1"
        />
        <p className="mb-5 text-xs text-label2">Mindestens 10 Zeichen.</p>

        <button type="submit" disabled={submitting || !token} className="btn-ap-capsule btn-ap-capsule-primary w-full">
          {submitting ? "Registrieren…" : "Zugang einrichten"}
        </button>
      </form>
    </PartnerAuthShell>
  );
}
