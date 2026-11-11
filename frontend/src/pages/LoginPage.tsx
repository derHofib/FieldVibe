import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";
import Blueprint from "../components/Blueprint";
import { Logo } from "../components/brand/Logo";
import { RechtlicheLinks } from "../components/RechtlicheLinks";

export function LoginPage() {
  const { login, loginMfa } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mfaToken) {
        await loginMfa(mfaToken, code);
      } else {
        const zwischenToken = await login(email, password);
        if (zwischenToken) {
          setMfaToken(zwischenToken);
          return;
        }
      }
      // "/" leitet je Rolle zur Startseite um (Plattform-Dashboard, Feed, Papierkorb);
      // ein fester Pfad landet fuer Mandanten-Nutzer seit der 404-Seite dort.
      navigate("/", { replace: true });
    } catch (err) {
      // Abgelaufener Zwischen-Token (401): zurueck zur Passwort-Eingabe.
      if (mfaToken && err instanceof ApiError && err.status === 401 && !/Code/.test(err.message)) {
        zurueckZumPasswort();
      }
      setError(err instanceof ApiError ? err.message : "Anmeldung fehlgeschlagen");
    } finally {
      setSubmitting(false);
    }
  }

  function zurueckZumPasswort() {
    setMfaToken(null);
    setCode("");
    setPassword("");
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-card p-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm">
        <div className="mb-6 flex justify-center">
          <Logo variante="wortmarke" hoehe={32} />
        </div>

        <Blueprint className="bg-card p-8">
          <h1 className="mb-6 text-center font-heading text-zeile font-semibold uppercase tracking-[0.14em] text-label2">
            Anmeldung
          </h1>

          {error && (
            <div className="mb-4 border rounded-[var(--radius-ap-md)] border-st-fehlt px-3 py-2 text-fliess text-st-fehlt ">
              {error}
            </div>
          )}

          {mfaToken ? (
            <>
              <p className="mb-4 text-sekundaer text-label2">
                Gib den 6-stelligen Code aus deiner Authenticator-App ein – oder einen deiner
                Wiederherstellungscodes.
              </p>
              <label htmlFor="mfa-code" className="mb-1 block text-fliess font-medium text-label">
                Code
              </label>
              <input
                id="mfa-code"
                type="text"
                required
                autoFocus
                autoComplete="one-time-code"
                inputMode="text"
                autoCapitalize="characters"
                spellCheck={false}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="field-ap btn-touch mb-6 tracking-widest"
              />
            </>
          ) : (
            <>
              <label htmlFor="login-email" className="mb-1 block text-fliess font-medium text-label">E-Mail</label>
              <input
                id="login-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="field-ap btn-touch mb-4"
              />

              <label htmlFor="login-passwort" className="mb-1 block text-fliess font-medium text-label">Passwort</label>
              <input
                id="login-passwort"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="field-ap btn-touch mb-6"
              />
            </>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="btn-touch btn-ap-primary w-full py-2 disabled:opacity-50"
          >
            {submitting ? "Anmelden…" : mfaToken ? "Bestätigen" : "Anmelden"}
          </button>

          {mfaToken && (
            <button
              type="button"
              onClick={() => {
                zurueckZumPasswort();
                setError(null);
              }}
              className="mt-4 block w-full text-center text-sekundaer text-label2 hover:text-label"
            >
              Zurück
            </button>
          )}

          <Link to="/passwort-vergessen" className="mt-4 block text-center text-sekundaer text-label2 hover:text-label">
            Passwort vergessen?
          </Link>
        </Blueprint>
        <RechtlicheLinks className="mt-6" />
      </form>
    </div>
  );
}
