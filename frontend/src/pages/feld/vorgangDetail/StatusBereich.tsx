import { UserCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { bestaetigen } from "../../../components/apple/BestaetigungsDialog";
import { useAuth } from "../../../context/AuthContext";
import type { Leistungstyp, Vorgang, VorgangStatus } from "../../../types";
import { LEISTUNGSTYPEN, PRIORITAET_OPTIONEN, STATUS_LABEL, STATUS_OPTIONS, VORGANG_STATUS_GESCHLOSSEN } from "./konstanten";
import type { UebersichtDaten } from "./useVorgangUebersicht";

interface StatusBereichProps {
  vorgang: Vorgang;
  uebersichtDaten: UebersichtDaten;
}

/** Beschreibung, Status, Priorität, Übernahme sowie die Dialoge für „Wartet auf Kunde“ und Folge-Vorgang. */
export function StatusBereich({ vorgang, uebersichtDaten }: StatusBereichProps) {
  const {
    folgeAuftraege, folgeAuftragLeistungstyp, folgeAuftragMutation, folgeVorgangId,
    mandantEinstellungen, prioritaetMutation, setFolgeAuftragLeistungstyp,
    setShowFolgeAuftragDialog, setShowWartetKundeDialog, setWiedervorlageTage,
    showFolgeAuftragDialog, showWartetKundeDialog, statusMutation, uebernehmenMutation,
    wiedervorlageTage,
  } = uebersichtDaten;
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  return (
    <>
      {vorgang.beschreibung && (
        <p className="mt-2 text-sm text-label">{vorgang.beschreibung}</p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label htmlFor="vorgang-status-select" className="text-sm text-label2">
          Status:
        </label>
        <select
          id="vorgang-status-select"
          value={vorgang.status}
          onChange={(e) => {
            const status = e.target.value as VorgangStatus;
            if (status === "wartet_kunde") {
              setWiedervorlageTage("");
              setShowWartetKundeDialog(true);
              return;
            }
            statusMutation.mutate({ status });
          }}
          className="btn-touch border border-sep bg-transparent px-2 py-1 text-sm text-label"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
        {vorgang.dauerauftrag_id ? (
          <span
            title="Wird beim Dauerauftrag automatisch anhand der Fälligkeit berechnet"
            className="border border-sep px-2 py-1 text-xs text-label"
          >
            Priorität {vorgang.prioritaet} (automatisch)
          </span>
        ) : (
          <label className="flex items-center gap-1 text-sm text-label2">
            Priorität
            <select
              value={vorgang.prioritaet}
              disabled={VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status) || prioritaetMutation.isPending}
              onChange={(e) => prioritaetMutation.mutate(Number(e.target.value))}
              className="btn-touch border border-sep bg-transparent px-2 py-1 text-sm text-label"
            >
              {PRIORITAET_OPTIONEN.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
        )}
        <button
          onClick={() => {
            setFolgeAuftragLeistungstyp("stoerung");
            setShowFolgeAuftragDialog(true);
          }}
          className="btn-touch border border-sepstrong px-3 py-1 text-xs font-medium text-label hover:bg-fill"
        >
          + Folge-Vorgang
        </button>
      </div>

      {!VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status) && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-label2">
            {vorgang.zugewiesener_name ? (
              <>
                Zugewiesen an: <span className="font-medium text-label">{vorgang.zugewiesener_name}</span>
              </>
            ) : (
              "Nicht zugewiesen"
            )}
          </span>
          {currentUser?.darf_vorgaenge_selbst_uebernehmen && (
            <button
              onClick={async () => {
                if (
                  vorgang.zugewiesener_user_id &&
                  vorgang.zugewiesener_user_id !== currentUser.id &&
                  !await bestaetigen(
                    `Dieser Vorgang ist bereits "${vorgang.zugewiesener_name}" zugewiesen. Trotzdem an mich übernehmen?`,
                  )
                ) {
                  return;
                }
                uebernehmenMutation.mutate();
              }}
              disabled={uebernehmenMutation.isPending || vorgang.zugewiesener_user_id === currentUser.id}
              className="btn-touch btn-ap-primary flex items-center gap-1 px-3 py-1.5 text-xs disabled:cursor-not-allowed"
            >
              <UserCheck size={13} strokeWidth={2} />
              {vorgang.zugewiesener_user_id === currentUser.id ? "Von mir übernommen" : "Ticket übernehmen"}
            </button>
          )}
        </div>
      )}

      {showWartetKundeDialog && (
        <div className="mt-2 space-y-2 border border-sepstrong p-2">
          <p className="text-sm text-label">
            Wartet auf Kunde: Nach wie vielen Tagen soll FieldVibe dich erinnern, nachzufragen?
          </p>
          <input
            type="number"
            min={1}
            placeholder={
              mandantEinstellungen
                ? mandantEinstellungen.effektive_wiedervorlage_standard_tage.toString()
                : "14"
            }
            value={wiedervorlageTage}
            onChange={(e) => setWiedervorlageTage(e.target.value)}
            className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
          />
          <div className="flex gap-2">
            <button
              onClick={() => {
                statusMutation.mutate({
                  status: "wartet_kunde",
                  wiedervorlageTage: wiedervorlageTage ? Number(wiedervorlageTage) : undefined,
                });
                setShowWartetKundeDialog(false);
              }}
              disabled={statusMutation.isPending}
              className="btn-touch btn-ap-primary flex-1 py-1.5 text-sm"
            >
              Übernehmen
            </button>
            <button
              onClick={() => setShowWartetKundeDialog(false)}
              className="btn-touch flex-1 btn-ap py-1.5 text-sm"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {showFolgeAuftragDialog && (
        <div className="mt-2 space-y-2 border border-sepstrong p-2">
          <p className="text-sm text-label">
            Folge-Vorgang anlegen: übernimmt Kunde/Anlage/Standort sowie offene Angebots-
            Materialpositionen dieses Vorgangs. Dieser Vorgang bleibt dabei unverändert.
          </p>
          <select
            value={folgeAuftragLeistungstyp}
            onChange={(e) => setFolgeAuftragLeistungstyp(e.target.value as Leistungstyp)}
            className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
          >
            {LEISTUNGSTYPEN.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
          <div className="flex gap-2">
            <button
              onClick={() => {
                folgeAuftragMutation.mutate(folgeAuftragLeistungstyp);
                setShowFolgeAuftragDialog(false);
              }}
              disabled={folgeAuftragMutation.isPending}
              className="btn-touch btn-ap-primary flex-1 py-1.5 text-sm"
            >
              Anlegen
            </button>
            <button
              onClick={() => setShowFolgeAuftragDialog(false)}
              className="btn-touch flex-1 btn-ap py-1.5 text-sm"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {folgeVorgangId && (
        <div className="mt-2 flex items-center justify-between rounded-md bg-st-erledigt-bg px-3 py-2 text-sm text-st-erledigt">
          <span>Folge-Vorgang wurde angelegt.</span>
          <button
            onClick={() => navigate(`/vorgaenge/${folgeVorgangId}`)}
            className="btn-touch font-medium underline"
          >
            Jetzt ansehen
          </button>
        </div>
      )}

      {folgeAuftraege && folgeAuftraege.length > 0 && (
        <div className="mt-2 space-y-1">
          <span className="text-xs font-medium text-label2">Folge-Vorgänge:</span>
          {folgeAuftraege.map((fa) => (
            <button
              key={fa.id}
              onClick={() => navigate(`/vorgaenge/${fa.id}`)}
              className="btn-touch block w-full border border-sep px-2 py-1.5 text-left text-sm text-label hover:bg-fill"
            >
              {fa.vorgangsnummer} · {fa.titel} · {STATUS_LABEL[fa.status]}
            </button>
          ))}
        </div>
      )}
    </>
  );
}
