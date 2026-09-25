import { Hexagon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { authApi } from "../api/endpoints";
import { ApiError } from "../api/client";
import Blueprint from "../components/Blueprint";
import { useAuth } from "../context/AuthContext";

export function RegistrierenPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const { loginMitToken } = useAuth();
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
      const tokens = await authApi.registrieren(token, name, password);
      await loginMitToken(tokens);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registrierung fehlgeschlagen");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-card p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <div className="flex h-[30px] w-[30px] shrink-0 items-center justify-center border border-sepstrong text-tint">
            <Hexagon size={17} strokeWidth={1.5} />
          </div>
          <span className="font-heading text-xl font-semibold uppercase tracking-wide text-label">
            Field<span className="text-tint">Vibe</span>
          </span>
        </div>

        <Blueprint className="bg-card p-8">
          <h1 className="mb-6 text-center font-heading text-sm font-semibold uppercase tracking-[0.14em] text-label2">
            Einladung annehmen
          </h1>

          {!token && (
            <p className="mb-4 border border-st-fehlt px-3 py-2 text-sm text-st-fehlt ">
              Der Link ist unvollständig. Bitte den Einladungslink erneut vom Absender anfordern.
            </p>
          )}

          <form onSubmit={handleSubmit}>
            {error && (
              <div className="mb-4 border border-st-fehlt px-3 py-2 text-sm text-st-fehlt ">
                {error}
              </div>
            )}

            <label className="mb-1 block text-sm font-medium text-label">Name</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="field-ap btn-touch mb-4"
            />

            <label className="mb-1 block text-sm font-medium text-label">Passwort</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="field-ap btn-touch mb-6"
            />

            <button
              type="submit"
              disabled={submitting || !token}
              className="btn-touch btn-ap-primary w-full py-2 disabled:opacity-50"
            >
              {submitting ? "Registrieren…" : "Konto erstellen"}
            </button>
          </form>
        </Blueprint>
      </div>
    </div>
  );
}
