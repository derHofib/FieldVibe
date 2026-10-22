import { useNavigate } from "react-router-dom";
import { SearchableSelect } from "../../../components/SearchableSelect";
import type { Vorgang } from "../../../types";
import { FREIGABE_FARBE, FREIGABE_LABEL } from "./konstanten";
import type { PartnerDaten } from "./useVorgangPartner";

interface PartnerAbschnittProps {
  istAktiverTab: (ziel: string) => boolean;
  tabPanelProps: (ziel: string) => { role?: "tabpanel"; "aria-labelledby"?: string };
  vorgang: Vorgang;
  partnerDaten: PartnerDaten;
}

/** Nachunternehmer zuweisen, Freigabestatus anzeigen, Zuweisung aufheben. */
export function PartnerAbschnitt({
  istAktiverTab, tabPanelProps, vorgang, partnerDaten,
}: PartnerAbschnittProps) {
  const {
    partnerAufhebenMutation, partnerAuswahl, partnerHonorar, partnerListe, partnerWarnung,
    partnerZuweisenMutation, setPartnerAuswahl, setPartnerHonorar, setShowPartnerForm,
    showPartnerForm, zugewiesenerPartner,
  } = partnerDaten;
  const navigate = useNavigate();
  return (
    <div
      className={`card-ap p-3 ${istAktiverTab("abschnitt-uebersicht") ? "" : "hidden"}`}
      {...tabPanelProps("abschnitt-uebersicht")}
    >
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-heading text-sm font-semibold uppercase tracking-wide text-label">Nachunternehmer</h2>
        {!vorgang.partner_id && (
          <button
            onClick={() => setShowPartnerForm((v) => !v)}
            className="btn-touch text-xs font-medium text-tint"
          >
            {showPartnerForm ? "Abbrechen" : "+ Zuweisen"}
          </button>
        )}
      </div>

      {partnerWarnung && (
        <p className="mb-2 rounded-md bg-st-arbeit-bg px-3 py-2 text-xs text-st-arbeit">
          Für diesen Partner liegt keine gültige Freistellungsbescheinigung vor -- ohne sie greift bei
          Zahlungen für Bauleistungen grundsätzlich die 15%-Bauabzugsteuer nach § 48 EStG.
        </p>
      )}

      {vorgang.partner_id ? (
        <div className="flex items-center justify-between border border-sepstrong px-3 py-2">
          <div>
            <button
              onClick={() => navigate(`/partner/${vorgang.partner_id}`)}
              className="text-sm font-medium text-label hover:underline"
            >
              {zugewiesenerPartner?.name ?? "…"}
            </button>
            {vorgang.partner_honorar_netto && (
              <div className="text-xs text-label2">
                Honorar: {vorgang.partner_honorar_netto} EUR netto
              </div>
            )}
            {vorgang.partner_freigabe_status === "abgelehnt" && vorgang.partner_ablehnung_grund && (
              <div className="text-xs text-st-fehlt">
                Grund: {vorgang.partner_ablehnung_grund}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {vorgang.partner_freigabe_status && (
              <span
                className={`rounded-full px-2 py-1 text-xs font-semibold ${FREIGABE_FARBE[vorgang.partner_freigabe_status]}`}
              >
                {FREIGABE_LABEL[vorgang.partner_freigabe_status]}
              </span>
            )}
            <button
              onClick={() => partnerAufhebenMutation.mutate()}
              disabled={partnerAufhebenMutation.isPending}
              className="btn-touch text-xs text-st-fehlt"
            >
              Aufheben
            </button>
          </div>
        </div>
      ) : (
        !showPartnerForm && (
          <p className="text-sm text-label2">Kein Nachunternehmer zugewiesen.</p>
        )
      )}

      {showPartnerForm && (
        <div className="space-y-2 border border-sepstrong p-2">
          <SearchableSelect
            value={partnerAuswahl}
            onChange={setPartnerAuswahl}
            placeholder="Partner wählen…"
            options={(partnerListe ?? []).map((p) => ({
              value: p.id,
              label: p.name,
              sublabel: p.gewerk ?? undefined,
            }))}
          />
          <input
            type="number"
            step="0.01"
            min="0"
            value={partnerHonorar}
            onChange={(e) => setPartnerHonorar(e.target.value)}
            placeholder="Honorar netto (optional)"
            className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
          />
          <button
            disabled={!partnerAuswahl || partnerZuweisenMutation.isPending}
            onClick={() => partnerZuweisenMutation.mutate()}
            className="btn-touch btn-ap-primary w-full px-3 py-1.5 text-sm"
          >
            Zuweisen
          </button>
        </div>
      )}
    </div>
  );
}
