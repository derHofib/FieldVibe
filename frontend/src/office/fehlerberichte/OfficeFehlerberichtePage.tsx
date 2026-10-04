import { useParams } from "react-router-dom";

import { FehlerberichtDetailAnsicht } from "../../components/fehlerberichte/FehlerberichtDetailAnsicht";
import { FehlerberichtListe } from "../../components/fehlerberichte/FehlerberichtListe";
import { useAuth } from "../../context/AuthContext";
import { SeitenKopf } from "../OfficeUi";

const detailPfad = (id: string) => `/fehlerberichte/${id}`;

export function OfficeFehlerberichtePage() {
  return (
    <div className="mx-auto max-w-5xl">
      <SeitenKopf titel="Fehlerberichte" />
      <FehlerberichtListe mitMandantFilter={false} detailPfad={detailPfad} />
    </div>
  );
}

export function OfficeFehlerberichtDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { hatRecht } = useAuth();
  if (!id) return null;
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="sr-only">Fehlerbericht</h1>
      <FehlerberichtDetailAnsicht
        key={id}
        id={id}
        mitMandant={false}
        kannBearbeiten={hatRecht("fehlerberichte", "bearbeiten")}
        kannLoeschen={hatRecht("fehlerberichte", "loeschen")}
        listenPfad="/fehlerberichte"
        detailPfad={detailPfad}
      />
    </div>
  );
}
