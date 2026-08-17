import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";
import { Starfield } from "../components/Starfield";

export function LoginPage() {
  const { login } = useAuth();
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
      // Fuer Nicht-Platform-Admins faengt das Catch-All in App.tsx diesen
      // Pfad ab und leitet zur echten Startseite (Feed/Papierkorb) um.
      navigate("/uebersicht", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Anmeldung fehlgeschlagen");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950">
      <Starfield />

      <form
        onSubmit={handleSubmit}
        className="relative w-full max-w-sm rounded-xl border border-cyan-400/20 bg-slate-900/60 p-8 shadow-[0_0_45px_-10px_rgba(34,211,238,0.25)] backdrop-blur-xl"
      >
        <h1 className="mb-6 text-xl font-bold tracking-wide text-white">
          FieldVibe <span className="text-cyan-400">Anmeldung</span>
        </h1>

        {error && (
          <div className="mb-4 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        <label className="mb-1 block text-sm font-medium text-slate-300">E-Mail</label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="btn-touch mb-4 w-full rounded-md border border-slate-700 bg-slate-800/60 px-3 py-2 text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-hidden focus:ring-1 focus:ring-cyan-400/60"
        />

        <label className="mb-1 block text-sm font-medium text-slate-300">Passwort</label>
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="btn-touch mb-6 w-full rounded-md border border-slate-700 bg-slate-800/60 px-3 py-2 text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-hidden focus:ring-1 focus:ring-cyan-400/60"
        />

        <button
          type="submit"
          disabled={submitting}
          className="btn-touch w-full rounded-md bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-2 font-medium text-white shadow-[0_0_20px_-5px_rgba(34,211,238,0.6)] hover:from-cyan-400 hover:to-blue-500 disabled:opacity-50"
        >
          {submitting ? "Anmelden…" : "Anmelden"}
        </button>
      </form>
    </div>
  );
}
