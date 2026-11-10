import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { authApi } from "../api/endpoints";
import Blueprint from "../components/Blueprint";
import { Logo } from "../components/brand/Logo";
import { RechtlicheLinks } from "../components/RechtlicheLinks";
import { MIN_PASSWORT_LAENGE } from "../utils/passwort";

export function ResetPasswordPage() {
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
      await authApi.passwortZuruecksetzen(token, password);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Zurücksetzen fehlgeschlagen");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-card p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex justify-center">
          <Logo variante="wortmarke" hoehe={32} />
        </div>

        <Blueprint className="bg-card p-8">
          <h1 className="mb-6 text-center font-heading text-sm font-semibold uppercase tracking-[0.14em] text-label2">
            Neues Passwort setzen
          </h1>

          {!token && (
            <p className="mb-4 border border-st-fehlt px-3 py-2 text-sm text-st-fehlt">
              Der Link ist unvollständig. Bitte fordere einen neuen an.
            </p>
          )}

          {done ? (
            <>
              <p className="mb-4 border border-st-erledigt px-3 py-2 text-sm text-st-erledigt">
                Passwort erfolgreich geändert. Du kannst dich jetzt anmelden.
              </p>
              <button
                onClick={() => navigate("/login")}
                className="btn-touch btn-ap-primary w-full py-2"
              >
                Zur Anmeldung
              </button>
            </>
          ) : (
            <form onSubmit={handleSubmit}>
              {error && (
                <div className="mb-4 border border-st-fehlt px-3 py-2 text-sm text-st-fehlt">
                  {error}
                </div>
              )}
              <label htmlFor="reset-password" className="mb-1 block text-sm font-medium text-label">
                Neues Passwort
              </label>
              <input
                id="reset-password"
                type="password"
                required
                minLength={MIN_PASSWORT_LAENGE}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="field-ap btn-touch mb-1"
              />
              <p className="mb-4 text-xs text-label2">Mindestens {MIN_PASSWORT_LAENGE} Zeichen.</p>
              <button
                type="submit"
                disabled={submitting || !token}
                className="btn-touch btn-ap-primary w-full py-2 disabled:opacity-50"
              >
                {submitting ? "Speichern…" : "Passwort speichern"}
              </button>
            </form>
          )}

          {!done && (
            <Link
              to="/passwort-vergessen"
              className="mt-4 block text-center text-sm text-label2 hover:text-label"
            >
              Neuen Link anfordern
            </Link>
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
