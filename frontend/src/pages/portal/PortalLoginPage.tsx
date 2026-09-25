import { useQuery } from "@tanstack/react-query";
import { Hexagon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { kundenportalAuthApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import Blueprint from "../../components/Blueprint";
import { useKundenAuth } from "../../context/KundenAuthContext";

export function PortalLoginPage() {
  const { login } = useKundenAuth();
  const navigate = useNavigate();
  const { slug } = useParams<{ slug?: string }>();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Personalisierter Link (/portal/l/:slug): ein Link pro Kunde, den jeder
  // Mitarbeiter dieses Kunden nutzen kann -- begruesst nur mit Name/Logo des
  // Kunden zur Wiedererkennung, befuellt aber keine E-Mail (da nicht an
  // eine einzelne Person gebunden). Passwort-Eingabe bleibt Pflicht.
  const { data: linkInfo } = useQuery({
    queryKey: ["kundenportal-link", slug],
    queryFn: () => kundenportalAuthApi.linkInfo(slug!),
    enabled: !!slug,
    retry: false,
  });
  const { data: logoInfo } = useQuery({
    queryKey: ["kundenportal-link-logo", slug],
    queryFn: () => kundenportalAuthApi.linkLogoUrl(slug!),
    enabled: !!slug && !!linkInfo?.hat_logo,
    retry: false,
  });

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/portal/vorgaenge", { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Anmeldung fehlgeschlagen. Bitte E-Mail und Passwort prüfen oder \"Passwort vergessen?\" unten nutzen.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-card p-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <div className="flex h-[30px] w-[30px] shrink-0 items-center justify-center border border-sepstrong text-tint">
            <Hexagon size={17} strokeWidth={1.5} />
          </div>
          <span className="font-heading text-xl font-semibold uppercase tracking-wide text-label">
            Kunden<span className="text-tint">portal</span>
          </span>
        </div>

        <Blueprint className="bg-card p-8">
          {logoInfo?.url && (
            <img
              src={logoInfo.url}
              alt={`Logo ${linkInfo?.kunde_name ?? ""}`}
              className="mx-auto mb-4 h-16 w-16 object-contain"
            />
          )}
          <p className="mb-6 text-center text-sm text-label2">
            {linkInfo
              ? `Willkommen, ${linkInfo.kunde_name} – bitte mit Ihrer E-Mail und Ihrem Passwort anmelden.`
              : "Anmeldung für Ihre Aufträge, Angebote und Rechnungen"}
          </p>

          {error && (
            <div className="mb-4 border border-st-fehlt px-3 py-2 text-sm text-st-fehlt ">
              {error}
            </div>
          )}

          <label htmlFor="portal-login-email" className="mb-1 block text-sm font-medium text-label">
            E-Mail
          </label>
          <input
            id="portal-login-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="field-ap btn-touch mb-4"
          />

          <label htmlFor="portal-login-password" className="mb-1 block text-sm font-medium text-label">
            Passwort
          </label>
          <input
            id="portal-login-password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="field-ap btn-touch mb-6"
          />

          <button
            type="submit"
            disabled={submitting}
            className="btn-touch btn-ap-primary w-full py-2 disabled:opacity-50"
          >
            {submitting ? "Anmelden…" : "Anmelden"}
          </button>

          <Link to="/portal/passwort-vergessen" className="mt-4 block text-center text-sm text-label2 hover:text-label">
            Passwort vergessen?
          </Link>
        </Blueprint>
      </form>
    </div>
  );
}
