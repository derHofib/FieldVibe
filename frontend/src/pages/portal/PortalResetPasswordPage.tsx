import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { kundenportalAuthApi } from "../../api/endpoints";
import { Starfield } from "../../components/Starfield";

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
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950">
      <Starfield />
      <div className="relative w-full max-w-sm rounded-xl border border-cyan-400/20 bg-slate-900/60 p-8 shadow-[0_0_45px_-10px_rgba(34,211,238,0.25)] backdrop-blur-xl">
        <h1 className="mb-6 text-xl font-bold text-white">Neues Passwort setzen</h1>

        {!token && (
          <p className="mb-4 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            Der Link ist unvollständig. Bitte fordern Sie einen neuen an.
          </p>
        )}

        {done ? (
          <>
            <p className="mb-4 rounded-md border border-green-500/30 bg-green-500/10 px-3 py-2 text-sm text-green-300">
              Passwort erfolgreich geändert. Sie können sich jetzt anmelden.
            </p>
            <button
              onClick={() => navigate("/portal/login")}
              className="btn-touch w-full rounded-md bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-2 font-medium text-white shadow-[0_0_20px_-5px_rgba(34,211,238,0.6)] hover:from-cyan-400 hover:to-blue-500"
            >
              Zur Anmeldung
            </button>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            {error && (
              <div className="mb-4 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                {error}
              </div>
            )}
            <label className="mb-1 block text-sm font-medium text-slate-300">Neues Passwort</label>
            <input
              type="password"
              required
              minLength={10}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="btn-touch mb-4 w-full rounded-md border border-slate-700 bg-slate-800/60 px-3 py-2 text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-hidden focus:ring-1 focus:ring-cyan-400/60"
            />
            <button
              type="submit"
              disabled={submitting || !token}
              className="btn-touch w-full rounded-md bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-2 font-medium text-white shadow-[0_0_20px_-5px_rgba(34,211,238,0.6)] hover:from-cyan-400 hover:to-blue-500 disabled:opacity-50"
            >
              {submitting ? "Speichern…" : "Passwort speichern"}
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
