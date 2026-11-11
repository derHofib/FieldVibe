import { Ban, Lock, SearchX, WifiOff } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { EmptyState } from "./EmptyState";

export type FehlerArt = "kein_zugriff" | "nicht_gefunden" | "netz" | "sonst";

export function fehlerArt(fehler: unknown): FehlerArt {
  if (fehler instanceof ApiError) {
    if (fehler.status === 403) return "kein_zugriff";
    if (fehler.status === 404) return "nicht_gefunden";
    return "sonst";
  }
  // fetch wirft bei Verbindungsabbruch/Timeout keinen ApiError.
  return "netz";
}

const TEXTE: Record<FehlerArt, (was: string) => string> = {
  kein_zugriff: () => "Kein Zugriff: Dir fehlt das Recht für diese Ansicht.",
  nicht_gefunden: (was) => `${was} nicht gefunden oder kein Zugriff.`,
  netz: () => "Keine Verbindung zum Server. Bitte prüfe deine Internetverbindung.",
  sonst: (was) => `${was} konnte nicht geladen werden.`,
};

/** Vierter Zustand jeder Datenansicht (neben Laden/Inhalt/leer): ein fehlgeschlagener Abruf
 * darf weder wie "leer" noch wie endloses Laden aussehen. `was` im Nominativ mit Artikel
 * steht am Satzanfang, z. B. "Der Kunde". */
export function FehlerZustand({
  fehler,
  onErneut,
  was = "Die Daten",
  zurueck = false,
  className = "",
}: {
  fehler: unknown;
  onErneut?: () => void;
  was?: string;
  /** Detailseiten: zusaetzlich "Zurück" anbieten. */
  zurueck?: boolean;
  className?: string;
}) {
  const navigate = useNavigate();
  const art = fehlerArt(fehler);
  const icon = { kein_zugriff: Lock, nicht_gefunden: SearchX, netz: WifiOff, sonst: Ban }[art];
  // Bei 403/404 bringt ein erneuter Versuch nichts.
  const erneutSinnvoll = !!onErneut && art !== "kein_zugriff" && art !== "nicht_gefunden";
  const text = TEXTE[art](was);

  return (
    <div role="alert" className={className}>
      <EmptyState
        icon={icon}
        text={text}
        action={
          erneutSinnvoll || zurueck ? (
            <>
              {zurueck && (
                <button type="button" className="btn-touch btn-ap px-4" onClick={() => navigate(-1)}>
                  Zurück
                </button>
              )}
              {erneutSinnvoll && (
                <button type="button" className="btn-touch btn-ap btn-ap-primary px-4" onClick={onErneut}>
                  Erneut versuchen
                </button>
              )}
            </>
          ) : undefined
        }
      />
    </div>
  );
}
