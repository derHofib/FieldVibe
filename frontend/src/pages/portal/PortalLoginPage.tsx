import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { kundenportalAuthApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { Starfield } from "../../components/Starfield";
import { useKundenAuth } from "../../context/KundenAuthContext";

export function PortalLoginPage() {
  const { login } = useKundenAuth();
  const navigate = useNavigate();
  const { slug } = useParams<{ slug?: string }>();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Personalisierter Link (/portal/l/:slug): befuellt nur die E-Mail und
  // begruesst mit Namen -- ersetzt nicht die Passwort-Eingabe.
  const { data: linkInfo } = useQuery({
    queryKey: ["kundenportal-link", slug],
    queryFn: () => kundenportalAuthApi.linkInfo(slug!),
    enabled: !!slug,
    retry: false,
  });
  useEffect(() => {
    if (linkInfo) setEmail(linkInfo.email);
  }, [linkInfo]);

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
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950">
      <Starfield />

      <form
        onSubmit={handleSubmit}
        className="relative w-full max-w-sm rounded-xl border border-cyan-400/20 bg-slate-900/60 p-8 shadow-[0_0_45px_-10px_rgba(34,211,238,0.25)] backdrop-blur-xl"
      >
        <h1 className="mb-1 text-xl font-bold tracking-wide text-white">
          Kunden<span className="text-cyan-400">portal</span>
        </h1>
        <p className="mb-6 text-sm text-slate-400">
          {linkInfo
            ? `Willkommen zurück, ${linkInfo.name} (${linkInfo.mandant_name}) – bitte mit Ihrem Passwort anmelden.`
            : "Anmeldung für Ihre Aufträge, Angebote und Rechnungen"}
        </p>

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
          className="btn-touch mb-4 w-full rounded-md border border-slate-700 bg-slate-800/60 px-3 py-2 text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none focus:ring-1 focus:ring-cyan-400/60"
        />

        <label className="mb-1 block text-sm font-medium text-slate-300">Passwort</label>
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="btn-touch mb-6 w-full rounded-md border border-slate-700 bg-slate-800/60 px-3 py-2 text-white placeholder:text-slate-500 focus:border-cyan-400/60 focus:outline-none focus:ring-1 focus:ring-cyan-400/60"
        />

        <button
          type="submit"
          disabled={submitting}
          className="btn-touch w-full rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-2 font-medium text-white shadow-[0_0_20px_-5px_rgba(34,211,238,0.6)] hover:from-cyan-400 hover:to-blue-500 disabled:opacity-50"
        >
          {submitting ? "Anmelden…" : "Anmelden"}
        </button>

        <Link to="/portal/passwort-vergessen" className="mt-4 block text-center text-sm text-slate-400 hover:text-slate-300">
          Passwort vergessen?
        </Link>
      </form>
    </div>
  );
}
