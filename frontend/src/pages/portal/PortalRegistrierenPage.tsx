import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { kundenportalAuthApi } from "../../api/endpoints";
import Blueprint from "../../components/Blueprint";
import { useKundenAuth } from "../../context/KundenAuthContext";

export function PortalRegistrierenPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const { loginMitToken } = useKundenAuth();
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
      const tokens = await kundenportalAuthApi.registrieren(token, name, password);
      await loginMitToken(tokens);
      navigate("/portal/vorgaenge", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registrierung fehlgeschlagen");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-ind-bg p-4">
      <Blueprint className="w-full max-w-sm bg-ind-bg p-8">
        <h1 className="mb-6 font-heading text-xl font-semibold uppercase tracking-wide text-ind-ink">
          Kunden<span className="text-ind-acc-txt">portal</span> — Zugang einrichten
        </h1>

        {!token && (
          <p className="mb-4 border border-red-500/40 px-3 py-2 text-sm text-red-600 dark:text-red-400">
            Der Link ist unvollständig. Bitte den Einladungslink erneut vom Betrieb anfordern.
          </p>
        )}

        <form onSubmit={handleSubmit}>
          {error && (
            <div className="mb-4 border border-red-500/40 px-3 py-2 text-sm text-red-600 dark:text-red-400">
              {error}
            </div>
          )}

          <label className="mb-1 block text-sm font-medium text-ind-ink-2">Name</label>
          <input required value={name} onChange={(e) => setName(e.target.value)} className="input-industry btn-touch mb-4" />

          <label className="mb-1 block text-sm font-medium text-ind-ink-2">Passwort</label>
          <input
            type="password"
            required
            minLength={10}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="input-industry btn-touch mb-6"
          />

          <button
            type="submit"
            disabled={submitting || !token}
            className="btn-touch btn-industry btn-industry-primary w-full py-2 disabled:opacity-50"
          >
            {submitting ? "Registrieren…" : "Zugang einrichten"}
          </button>
        </form>
      </Blueprint>
    </div>
  );
}
