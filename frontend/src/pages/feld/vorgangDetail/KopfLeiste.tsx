import { AlertTriangle, Building2, Clock, UserPlus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { bestaetigen } from "../../../components/apple/BestaetigungsDialog";
import { useAuth } from "../../../context/AuthContext";
import type { Anlage, Standort, Vorgang } from "../../../types";
import { heuteIso, tageZwischen } from "../../../utils/format";
import { VORGANG_STATUS_GESCHLOSSEN } from "./konstanten";

interface KopfLeisteProps {
  aktionsFehler: string | null;
  anlage: Anlage | undefined;
  deleteVorgangMutation: { mutate: () => void; isPending: boolean };
  setAktionsFehler: (wert: string | null) => void;
  standort: Standort | undefined;
  vorgang: Vorgang;
}

/** Zurück/Löschen, Aktionsfehler und Fakten-Leiste (Anlage, Fälligkeit, Zuweisung). */
export function KopfLeiste({
  aktionsFehler, anlage, deleteVorgangMutation, setAktionsFehler, standort, vorgang,
}: KopfLeisteProps) {
  const navigate = useNavigate();
  const { hatRecht } = useAuth();
  const kannLoeschen = hatRecht("vorgaenge", "loeschen");
  return (
    <>
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
          ← Zurück
        </button>
        {kannLoeschen && (
          <button
            onClick={async () => {
              if (await bestaetigen("Vorgang wirklich löschen? Verknüpfte Daten wandern in den Papierkorb.")) {
                deleteVorgangMutation.mutate();
              }
            }}
            disabled={deleteVorgangMutation.isPending}
            className="btn-touch text-sm font-medium text-st-fehlt disabled:opacity-50"
          >
            Vorgang löschen
          </button>
        )}
      </div>

      {aktionsFehler && (
        <div className="flex items-center justify-between gap-2 border border-st-fehlt px-3 py-2 text-sm text-st-fehlt">
          <span className="flex items-center gap-1.5">
            <AlertTriangle size={14} strokeWidth={1.5} /> {aktionsFehler}
          </span>
          <button onClick={() => setAktionsFehler(null)} className="btn-touch text-xs underline">
            Ausblenden
          </button>
        </div>
      )}

      {/* Fakten-Leiste: die wichtigsten Eckdaten auf einen Blick, bevor man
          in die Karte darunter eintaucht (siehe Design-Vorschlag "Feed und
          Detail neu gedacht"). */}
      {(anlage?.bezeichnung || standort?.bezeichnung || vorgang.faelligkeit_am || !vorgang.zugewiesener_user_id) && (
        <div className="flex flex-wrap gap-1.5">
          {(anlage?.bezeichnung || standort?.bezeichnung) && (
            <span className="flex items-center gap-1.5 border border-sep px-2.5 py-1 text-xs font-medium text-label">
              <Building2 size={13} strokeWidth={1.5} /> {anlage?.bezeichnung ?? standort?.bezeichnung}
            </span>
          )}
          {vorgang.faelligkeit_am && (
            <span
              className={`flex items-center gap-1.5 border px-2.5 py-1 text-xs font-medium ${
                vorgang.faelligkeit_am.slice(0, 10) < heuteIso() &&
                !VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status)
                  ? "border-st-fehlt text-st-fehlt"
                  : "border-sep text-label"
              }`}
            >
              <Clock size={13} strokeWidth={1.5} />
              {vorgang.faelligkeit_am.slice(0, 10) < heuteIso() &&
              !VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status)
                ? `${tageZwischen(vorgang.faelligkeit_am.slice(0, 10), heuteIso())} Tage überfällig`
                : `Fällig: ${new Date(vorgang.faelligkeit_am).toLocaleDateString("de-DE")}`}
            </span>
          )}
          {!vorgang.zugewiesener_user_id && !VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status) && (
            <span className="flex items-center gap-1.5 border border-dashed border-st-arbeit px-2.5 py-1 text-xs font-medium text-st-arbeit">
              <UserPlus size={13} strokeWidth={1.5} /> Nicht zugewiesen
            </span>
          )}
        </div>
      )}
    </>
  );
}
