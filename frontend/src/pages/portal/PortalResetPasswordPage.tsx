import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { kundenportalAuthApi } from "../../api/endpoints";

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
    <div className="flex min-h-screen items-center justify-center bg-slate-100">
      <div className="w-full max-w-sm rounded-lg bg-white p-8 shadow-md">
        <h1 className="mb-6 text-xl font-bold text-slate-800">Neues Passwort setzen</h1>

        {!token && (
          <p className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            Der Link ist unvollständig. Bitte fordern Sie einen neuen an.
          </p>
        )}

        {done ? (
          <>
            <p className="mb-4 rounded-md bg-green-50 px-3 py-2 text-sm text-green-700">
              Passwort erfolgreich geändert. Sie können sich jetzt anmelden.
            </p>
            <button
              onClick={() => navigate("/portal/login")}
              className="btn-touch w-full rounded-md bg-slate-900 px-3 py-2 font-medium text-white hover:bg-slate-800"
            >
              Zur Anmeldung
            </button>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            {error && (
              <div className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
            )}
            <label className="mb-1 block text-sm font-medium text-slate-700">Neues Passwort</label>
            <input
              type="password"
              required
              minLength={10}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="btn-touch mb-4 w-full rounded-md border border-slate-300 px-3 py-2"
            />
            <button
              type="submit"
              disabled={submitting || !token}
              className="btn-touch w-full rounded-md bg-slate-900 px-3 py-2 font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {submitting ? "Speichern…" : "Passwort speichern"}
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
