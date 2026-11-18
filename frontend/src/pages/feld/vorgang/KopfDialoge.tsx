import type { Dispatch, SetStateAction } from "react";
import type { NavigateFunction } from "react-router-dom";
import type { UseMutationResult } from "@tanstack/react-query";

import { Select } from "../../../components/apple/Select";
import type { Anlage, Kunde, Leistungstyp, MandantEinstellungen, Vorgang, VorgangStatus } from "../../../types";
import { LEISTUNGSTYPEN } from "./konstanten";

/** Inline-Formulare und Dialoge, die aus dem Kopf-Menü bzw. der Aktionsleiste
 * geöffnet werden. Sie hängen am Kopf statt am Übersicht-Tab, weil Status-
 * und Zuordnungsaktionen auf jedem Tab erreichbar sind. */
export function KopfDialoge({
  navigate,
  editingZuordnung,
  setEditingZuordnung,
  editKundeId,
  setEditKundeId,
  editAnlageId,
  setEditAnlageId,
  alleKunden,
  anlagenFuerEditKunde,
  zuordnungError,
  setZuordnungError,
  zuordnungMutation,
  showWartetKundeDialog,
  setShowWartetKundeDialog,
  mandantEinstellungen,
  wiedervorlageTage,
  setWiedervorlageTage,
  statusMutation,
  showFolgeAuftragDialog,
  setShowFolgeAuftragDialog,
  folgeAuftragLeistungstyp,
  setFolgeAuftragLeistungstyp,
  folgeAuftragMutation,
  folgeVorgangId,
}: {
  navigate: NavigateFunction;
  editingZuordnung: boolean;
  setEditingZuordnung: Dispatch<SetStateAction<boolean>>;
  editKundeId: string;
  setEditKundeId: Dispatch<SetStateAction<string>>;
  editAnlageId: string;
  setEditAnlageId: Dispatch<SetStateAction<string>>;
  alleKunden: Kunde[] | undefined;
  anlagenFuerEditKunde: Anlage[] | undefined;
  zuordnungError: string | null;
  setZuordnungError: Dispatch<SetStateAction<string | null>>;
  zuordnungMutation: UseMutationResult<Vorgang, Error, void, unknown>;
  showWartetKundeDialog: boolean;
  setShowWartetKundeDialog: Dispatch<SetStateAction<boolean>>;
  mandantEinstellungen: MandantEinstellungen | undefined;
  wiedervorlageTage: string;
  setWiedervorlageTage: Dispatch<SetStateAction<string>>;
  statusMutation: UseMutationResult<Vorgang | null, unknown, { status: VorgangStatus; wiedervorlageTage?: number | undefined }, unknown>;
  showFolgeAuftragDialog: boolean;
  setShowFolgeAuftragDialog: Dispatch<SetStateAction<boolean>>;
  folgeAuftragLeistungstyp: Leistungstyp;
  setFolgeAuftragLeistungstyp: Dispatch<SetStateAction<Leistungstyp>>;
  folgeAuftragMutation: UseMutationResult<Vorgang, unknown, Leistungstyp, unknown>;
  folgeVorgangId: string | null;
}) {
  return (
    <>
      {editingZuordnung && (
        <div className="space-y-2 border rounded-[var(--radius-ap-card)] border-sepstrong p-3">
          <div>
            <label className="mb-1 block text-sekundaer font-medium text-label2">Kunde</label>
            <Select
              value={editKundeId}
              onChange={(e) => {
                setEditKundeId(e.target.value);
                setEditAnlageId("");
              }}
            >
              {alleKunden?.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name} ({k.kundennummer})
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-sekundaer font-medium text-label2">Anlage (optional)</label>
            <Select value={editAnlageId} onChange={(e) => setEditAnlageId(e.target.value)}>
              <option value="">Keine Anlage</option>
              {anlagenFuerEditKunde?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.bezeichnung}
                </option>
              ))}
            </Select>
          </div>
          {zuordnungError && <p className="text-sekundaer text-st-fehlt">{zuordnungError}</p>}
          <div className="flex gap-2">
            <button
              onClick={() => zuordnungMutation.mutate()}
              disabled={!editKundeId || zuordnungMutation.isPending}
              className="btn-touch btn-ap-primary flex-1 py-1.5 text-sekundaer"
            >
              Speichern
            </button>
            <button
              onClick={() => {
                setEditingZuordnung(false);
                setZuordnungError(null);
              }}
              className="btn-touch flex-1 btn-ap py-1.5 text-sekundaer"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {showWartetKundeDialog && (
        <div className="space-y-2 border rounded-[var(--radius-ap-md)] border-sepstrong p-2">
          <p className="text-fliess text-label">
            Wartet auf Kunde: Nach wie vielen Tagen soll FieldVibe dich erinnern, nachzufragen?
          </p>
          <input
            type="number"
            min={1}
            placeholder={
              mandantEinstellungen ? mandantEinstellungen.effektive_wiedervorlage_standard_tage.toString() : "14"
            }
            value={wiedervorlageTage}
            onChange={(e) => setWiedervorlageTage(e.target.value)}
            className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
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
              className="btn-touch btn-ap-primary flex-1 py-1.5 text-sekundaer"
            >
              Übernehmen
            </button>
            <button onClick={() => setShowWartetKundeDialog(false)} className="btn-touch flex-1 btn-ap py-1.5 text-sekundaer">
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {showFolgeAuftragDialog && (
        <div className="space-y-2 border rounded-[var(--radius-ap-md)] border-sepstrong p-2">
          <p className="text-fliess text-label">
            Folge-Vorgang anlegen: übernimmt Kunde/Anlage/Standort sowie offene Angebots-
            Materialpositionen dieses Vorgangs. Dieser Vorgang bleibt dabei unverändert.
          </p>
          <Select
            value={folgeAuftragLeistungstyp}
            onChange={(e) => setFolgeAuftragLeistungstyp(e.target.value as Leistungstyp)}
          >
            {LEISTUNGSTYPEN.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </Select>
          <div className="flex gap-2">
            <button
              onClick={() => {
                folgeAuftragMutation.mutate(folgeAuftragLeistungstyp);
                setShowFolgeAuftragDialog(false);
              }}
              disabled={folgeAuftragMutation.isPending}
              className="btn-touch btn-ap-primary flex-1 py-1.5 text-sekundaer"
            >
              Anlegen
            </button>
            <button onClick={() => setShowFolgeAuftragDialog(false)} className="btn-touch flex-1 btn-ap py-1.5 text-sekundaer">
              Abbrechen
            </button>
          </div>
        </div>
      )}

      {folgeVorgangId && (
        <div className="flex items-center justify-between rounded-md bg-st-erledigt-bg px-3 py-2 text-fliess text-st-erledigt">
          <span>Folge-Vorgang wurde angelegt.</span>
          <button onClick={() => navigate(`/vorgaenge/${folgeVorgangId}`)} className="btn-touch font-medium underline">
            Jetzt ansehen
          </button>
        </div>
      )}
    </>
  );
}
