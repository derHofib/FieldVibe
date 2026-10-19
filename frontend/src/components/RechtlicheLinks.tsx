// Pflichtlinks nach §5 DDG / Art. 13 DSGVO. Die URLs kommen zur Build-Zeit
// (VITE_IMPRESSUM_URL / VITE_DATENSCHUTZ_URL), siehe .env.example.

type Props = {
  // Für die Auth-Seiten, die unabhängig vom Theme immer auf dunkler Fläche
  // stehen: text-tint-text ist im Hell-Modus auf diesem Hintergrund zu
  // kontrastarm.
  dunkel?: boolean;
  className?: string;
};

function Eintrag({
  label,
  url,
  envName,
  dunkel,
}: {
  label: string;
  url: string | undefined;
  envName: string;
  dunkel: boolean;
}) {
  const wert = url?.trim();
  if (wert) {
    return (
      <a
        href={wert}
        target="_blank"
        rel="noopener noreferrer"
        className={`underline underline-offset-2 ${
          dunkel ? "text-slate-300 hover:text-white" : "text-tint-text hover:opacity-80"
        }`}
      >
        {label}
      </a>
    );
  }
  // Kein toter Link in Produktion; in der Entwicklung ein Hinweis, damit die
  // fehlende Konfiguration auffällt.
  if (import.meta.env.DEV) {
    return (
      <span className={dunkel ? "text-slate-500" : "text-label3"} title={`${envName} ist nicht gesetzt`}>
        {label} (URL fehlt)
      </span>
    );
  }
  return null;
}

export function RechtlicheLinks({ dunkel = false, className = "" }: Props) {
  const impressum = import.meta.env.VITE_IMPRESSUM_URL;
  const datenschutz = import.meta.env.VITE_DATENSCHUTZ_URL;

  // Ohne jeden Link kein leerer Navigations-Landmark in Produktion.
  if (!import.meta.env.DEV && !impressum?.trim() && !datenschutz?.trim()) return null;

  return (
    <nav
      aria-label="Rechtliche Hinweise"
      className={`flex flex-wrap justify-center gap-x-4 gap-y-1 text-center text-[13px] ${
        dunkel ? "" : "text-label2"
      } ${className}`}
    >
      <Eintrag label="Impressum" url={impressum} envName="VITE_IMPRESSUM_URL" dunkel={dunkel} />
      <Eintrag label="Datenschutz" url={datenschutz} envName="VITE_DATENSCHUTZ_URL" dunkel={dunkel} />
    </nav>
  );
}
