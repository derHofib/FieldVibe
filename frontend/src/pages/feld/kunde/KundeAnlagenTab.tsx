import { EmptyState } from "../../../components/EmptyState";
import type { KundeProfil, Standort } from "../../../types";
import { AnlageAktivToggle, NeueAnlage } from "./KundeAnlagen";
import { LeistungsverzeichnisVerwaltung } from "./KundeLeistungsverzeichnis";
import { StandorteVerwaltung } from "./KundeStandorte";
import { Boxes } from "lucide-react";
import type { NavigateFunction } from "react-router-dom";

export function KundeAnlagenTab({
  id,
  kannVerwalten,
  profil,
  navigate,
  standorteFuerAnlagen,
}: {
  id: string | undefined;
  kannVerwalten: boolean;
  profil: KundeProfil;
  navigate: NavigateFunction;
  standorteFuerAnlagen: Standort[] | undefined;
}) {
  return (
    <>
    <StandorteVerwaltung kundeId={id!} kannVerwalten={kannVerwalten} />

    <LeistungsverzeichnisVerwaltung kundeId={id!} kundeName={profil.name} kannVerwalten={kannVerwalten} />

    <div>
      <h2 className="mb-2 text-fliess font-semibold text-label2">Anlagen</h2>
      {profil.anlagen.length === 0 ? (
        <EmptyState icon={Boxes} text="Keine Anlagen." className="py-4" />
      ) : (
        <div className="space-y-2">
          {profil.anlagen.map((a) => (
            <div
              key={a.id}
              className={`flex items-center justify-between card-ap p-3 ${
                a.aktiv ? "" : "opacity-60"
              }`}
            >
              <button onClick={() => navigate(`/anlagen/${a.id}`)} className="btn-touch flex-1 text-left">
                <div className="text-fliess font-medium text-label">{a.bezeichnung}</div>
                {a.anlagentyp && <div className="text-sekundaer text-label2">{a.anlagentyp}</div>}
              </button>
              {kannVerwalten && (
                <AnlageAktivToggle anlage={a} kundeId={id!} />
              )}
            </div>
          ))}
        </div>
      )}
      {kannVerwalten && (
        <div className="mt-2">
          <NeueAnlage
            kundeId={id!}
            standorte={(standorteFuerAnlagen ?? []).filter((s) => s.aktiv)}
          />
        </div>
      )}
    </div>

    </>
  );
}
