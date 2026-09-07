import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { kundenportalAuthApi } from "../../api/endpoints";
import Blueprint from "../../components/Blueprint";

export function PortalResetPasswordPage() {
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
      await kundenportalAuthApi.passwortZuruecksetzen(token, password);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Zurücksetzen fehlgeschlagen");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-ind-bg p-4">
      <Blueprint className="w-full max-w-sm bg-ind-bg p-8">
        <h1 className="mb-6 font-heading text-xl font-semibold uppercase tracking-wide text-ind-ink">
          Neues Passwort setzen
        </h1>

        {!token && (
          <p className="mb-4 border border-red-500/40 px-3 py-2 text-sm text-red-600 dark:text-red-400">
            Der Link ist unvollständig. Bitte fordern Sie einen neuen an.
          </p>
        )}

        {done ? (
          <>
            <p className="mb-4 border border-green-500/40 px-3 py-2 text-sm text-green-700 dark:text-green-400">
              Passwort erfolgreich geändert. Sie können sich jetzt anmelden.
            </p>
            <button
              onClick={() => navigate("/portal/login")}
              className="btn-touch btn-industry btn-industry-primary w-full py-2"
            >
              Zur Anmeldung
            </button>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            {error && (
              <div className="mb-4 border border-red-500/40 px-3 py-2 text-sm text-red-600 dark:text-red-400">
                {error}
              </div>
            )}
            <label className="mb-1 block text-sm font-medium text-ind-ink-2">Neues Passwort</label>
            <input
              type="password"
              required
              minLength={10}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input-industry btn-touch mb-4"
            />
            <button
              type="submit"
              disabled={submitting || !token}
              className="btn-touch btn-industry btn-industry-primary w-full py-2 disabled:opacity-50"
            >
              {submitting ? "Speichern…" : "Passwort speichern"}
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
