import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { useKundenAuth } from "../../context/KundenAuthContext";

export function PortalLoginPage() {
  const { login } = useKundenAuth();
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
      navigate("/portal/vorgaenge", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Anmeldung fehlgeschlagen");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100">
      <form onSubmit={handleSubmit} className="w-full max-w-sm rounded-lg bg-white p-8 shadow-md">
        <h1 className="mb-1 text-xl font-bold text-slate-800">Kundenportal</h1>
        <p className="mb-6 text-sm text-slate-500">Anmeldung für Ihre Aufträge, Angebote und Rechnungen</p>

        {error && <div className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

        <label className="mb-1 block text-sm font-medium text-slate-700">E-Mail</label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="btn-touch mb-4 w-full rounded-md border border-slate-300 px-3 py-2"
        />

        <label className="mb-1 block text-sm font-medium text-slate-700">Passwort</label>
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="btn-touch mb-6 w-full rounded-md border border-slate-300 px-3 py-2"
        />

        <button
          type="submit"
          disabled={submitting}
          className="btn-touch w-full rounded-md bg-slate-900 px-3 py-2 font-medium text-white hover:bg-slate-800 disabled:opacity-50"
        >
          {submitting ? "Anmelden…" : "Anmelden"}
        </button>

        <Link to="/portal/passwort-vergessen" className="mt-4 block text-center text-sm text-slate-500">
          Passwort vergessen?
        </Link>
      </form>
    </div>
  );
}
