import { useParams } from "react-router-dom";

import { FehlerberichtDetailAnsicht } from "../components/fehlerberichte/FehlerberichtDetailAnsicht";
import { FehlerberichtListe } from "../components/fehlerberichte/FehlerberichtListe";

const detailPfad = (id: string) => `/bugfixes/${id}`;

// Die h1 kommt aus dem Layout-Header (seitentitel), die Seite selbst
// rendert deshalb keine eigene.
export function BugfixesPage() {
  return <FehlerberichtListe mitMandantFilter detailPfad={detailPfad} />;
}

export function BugfixDetailPage() {
  const { id } = useParams<{ id: string }>();
  if (!id) return null;
  // super_admin hat alle Fehlerbericht-Rechte (require_recht laesst ihn durch).
  return (
    <div className="mx-auto max-w-4xl">
      <FehlerberichtDetailAnsicht
        key={id}
        id={id}
        mitMandant
        kannBearbeiten
        kannLoeschen
        listenPfad="/bugfixes"
        detailPfad={detailPfad}
      />
    </div>
  );
}
