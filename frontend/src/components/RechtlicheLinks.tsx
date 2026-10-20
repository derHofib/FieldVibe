import { Link } from "react-router-dom";

import { usePortalSlugAusUrl, useRechtliches } from "../hooks/useRechtliches";
import { aufloesenRechtlicheUrl, type RechtlicheSeite } from "../utils/rechtliches";

// Pflichtlinks nach §5 DDG / Art. 13 DSGVO (im Kundenportal zusaetzlich die
// Barrierefreiheitserklaerung nach BFSG). Reihenfolge je Link: URL aus den
// Firmendaten des Mandanten > Build-Env (VITE_IMPRESSUM_URL /
// VITE_DATENSCHUTZ_URL, siehe .env.example) > interne Platzhalter-Seite.
// Die Links stehen sofort mit dem Fallback da; die Firmendaten-URLs ziehen
// nach, sobald die Abfrage durch ist.

type Props = {
  // Für die Auth-Seiten, die unabhängig vom Theme immer auf dunkler Fläche
  // stehen: text-tint-text ist im Hell-Modus auf diesem Hintergrund zu
  // kontrastarm.
  dunkel?: boolean;
  className?: string;
  // Kunden-Login-Link (/portal/l/:slug) bzw. angemeldetes Kundenportal: legt
  // den zuständigen Mandanten fest. Ohne Angabe gilt ?portal_slug= der Seite.
  portalSlug?: string;
  // Link zur Barrierefreiheitserklaerung (BFSG): nur im Kundenportal, dem
  // Verbraucher-Frontend -- die Mitarbeiter-Oberflaechen zeigen ihn nicht.
  barrierefreiheit?: boolean;
};

function Eintrag({
  label,
  seite,
  firmendatenUrl,
  envUrl,
  portalSlug,
  dunkel,
}: {
  label: string;
  seite: RechtlicheSeite;
  firmendatenUrl: string | null | undefined;
  envUrl: string | undefined;
  portalSlug: string | undefined;
  dunkel: boolean;
}) {
  const { href, extern } = aufloesenRechtlicheUrl({ seite, firmendatenUrl, envUrl, portalSlug });
  const klasse = `underline underline-offset-2 ${
    dunkel ? "text-slate-300 hover:text-white" : "text-tint-text hover:opacity-80"
  }`;
  if (extern) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={klasse}>
        {label}
      </a>
    );
  }
  return (
    <Link to={href} className={klasse}>
      {label}
    </Link>
  );
}

export function RechtlicheLinks({ dunkel = false, className = "", portalSlug, barrierefreiheit = false }: Props) {
  const slugAusUrl = usePortalSlugAusUrl();
  const slug = portalSlug ?? slugAusUrl;
  const { data } = useRechtliches(slug);

  return (
    <nav
      aria-label="Rechtliche Hinweise"
      className={`flex flex-wrap justify-center gap-x-4 gap-y-1 text-center text-[13px] ${
        dunkel ? "" : "text-label2"
      } ${className}`}
    >
      <Eintrag
        label="Impressum"
        seite="impressum"
        firmendatenUrl={data?.impressum_url}
        envUrl={import.meta.env.VITE_IMPRESSUM_URL}
        portalSlug={slug}
        dunkel={dunkel}
      />
      <Eintrag
        label="Datenschutz"
        seite="datenschutz"
        firmendatenUrl={data?.datenschutz_url}
        envUrl={import.meta.env.VITE_DATENSCHUTZ_URL}
        portalSlug={slug}
        dunkel={dunkel}
      />
      {barrierefreiheit && (
        <Eintrag
          label="Barrierefreiheit"
          seite="barrierefreiheit"
          firmendatenUrl={data?.barrierefreiheit_url}
          envUrl={undefined}
          portalSlug={slug}
          dunkel={dunkel}
        />
      )}
    </nav>
  );
}
