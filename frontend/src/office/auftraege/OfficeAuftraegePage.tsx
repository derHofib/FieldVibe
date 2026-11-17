import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Layers, Plus, Search } from "lucide-react";
import { useId, useMemo, useState } from "react";

import { auftraegeApi, kundenApi, projekteApi } from "../../api/endpoints";
import { SearchableSelect } from "../../components/SearchableSelect";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { EmptyState } from "../../components/EmptyState";
import { SearchField } from "../../components/apple/SearchField";
import { NEU_BUTTON_KLASSE } from "../../components/FormularFeld";
import { useAuth } from "../../context/AuthContext";
import type { Auftrag } from "../../types";
import { SeitenKopf } from "../OfficeUi";
import { AuftraegeTabelle } from "./AuftraegeTabelle";
import { AuftragDetailPanel } from "./AuftragDetailPanel";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";

/** Tabellen-Ansicht aller Auftraege (Projekt->Auftrag->Vorgang, siehe
 * app/models/auftrag.py) -- analog zu OfficeVorgaengePage.tsx, aber ohne
 * die dortigen Ansichts-Umschalter (Liste/Kanban/Raster): bei der
 * erwarteten Auftrags-Anzahl reicht eine einzelne Tabelle. */
export function OfficeAuftraegePage() {
  const uid = useId();
  const queryClient = useQueryClient();
  const { hatRecht } = useAuth();
  const darfAnlegen = hatRecht("projekte", "erstellen");
  const [suche, setSuche] = useState("");
  const [zeigeNeuerAuftrag, setZeigeNeuerAuftrag] = useState(false);
  const [neuerTitel, setNeuerTitel] = useState("");
  const [neuerProjektId, setNeuerProjektId] = useState("");
  const [neuerKundeId, setNeuerKundeId] = useState("");
  const [ausgewaehlterAuftrag, setAusgewaehlterAuftrag] = useState<Auftrag | null>(null);

  const { data: auftraege, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["auftraege"],
    queryFn: () => auftraegeApi.list(),
  });

  const { data: projekte } = useQuery({
    queryKey: ["projekte"],
    queryFn: () => projekteApi.list(),
    enabled: zeigeNeuerAuftrag,
  });

  const { data: kunden } = useQuery({
    queryKey: ["kunden"],
    queryFn: () => kundenApi.list(),
    enabled: zeigeNeuerAuftrag,
  });

  // Die Liste wird vollständig geladen, daher genügt ein Client-Filter.
  const gefiltert = useMemo(() => {
    const q = suche.trim().toLowerCase();
    if (!q) return auftraege ?? [];
    return (auftraege ?? []).filter((a) => `${a.titel} ${a.kunde_name ?? ""}`.toLowerCase().includes(q));
  }, [auftraege, suche]);

  const auftragErstellen = useMutation({
    mutationFn: () =>
      auftraegeApi.create({
        titel: neuerTitel.trim(),
        projekt_id: neuerProjektId || undefined,
        kunde_id: neuerKundeId || undefined,
      }),
    onSuccess: () => {
      setZeigeNeuerAuftrag(false);
      setNeuerTitel("");
      setNeuerProjektId("");
      setNeuerKundeId("");
      queryClient.invalidateQueries({ queryKey: ["auftraege"] });
    },
  });

  return (
    <div>
      <SeitenKopf titel="Aufträge">
        <SearchField
          value={suche}
          onChange={setSuche}
          placeholder="Titel oder Kunde…"
          ariaLabel="Aufträge suchen"
          className="w-64"
        />
        {darfAnlegen && (
          <button onClick={() => setZeigeNeuerAuftrag(true)} className={NEU_BUTTON_KLASSE}>
            <Plus size={14} strokeWidth={2.5} aria-hidden="true" />
            Neuer Auftrag
          </button>
        )}
      </SeitenKopf>

      <AnlegenPanel offen={zeigeNeuerAuftrag} titel="Neuer Auftrag" onClose={() => setZeigeNeuerAuftrag(false)}>
        <form
          className="flex flex-col gap-3 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (neuerTitel.trim() && !auftragErstellen.isPending) auftragErstellen.mutate();
          }}
        >
          <div>
            <label htmlFor={`${uid}-0`} className="mb-1 block text-fliess font-medium text-label">
              Titel<span aria-hidden="true" className="text-st-fehlt"> *</span>
            </label>
            <input
              id={`${uid}-0`}
              autoFocus
              value={neuerTitel}
              onChange={(e) => setNeuerTitel(e.target.value)}
              placeholder="z. B. Elektro-Gewerk Sanierung Musterstraße"
              className="field-ap"
            />
          </div>
          <div>
            <label htmlFor={`${uid}-1`} className="mb-1 block text-fliess font-medium text-label">Projekt (optional)</label>
            <SearchableSelect
              id={`${uid}-1`}
              value={neuerProjektId}
              onChange={setNeuerProjektId}
              placeholder="Kein Projekt"
              options={(projekte ?? []).map((p) => ({ value: p.id, label: p.name }))}
            />
          </div>
          <div>
            <label htmlFor={`${uid}-2`} className="mb-1 block text-fliess font-medium text-label">Kunde (optional)</label>
            <SearchableSelect
              id={`${uid}-2`}
              value={neuerKundeId}
              onChange={setNeuerKundeId}
              placeholder="Kein Kunde"
              options={(kunden ?? []).map((k) => ({ value: k.id, label: k.name }))}
            />
          </div>
          {auftragErstellen.isError && (
            <p role="alert" className="text-sekundaer text-st-fehlt">Der Auftrag konnte nicht angelegt werden.</p>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setZeigeNeuerAuftrag(false)} className="btn-touch btn-ap px-4">
              Abbrechen
            </button>
            <button
              type="submit"
              disabled={!neuerTitel.trim() || auftragErstellen.isPending}
              className={NEU_BUTTON_KLASSE}
            >
              Anlegen
            </button>
          </div>
        </form>
      </AnlegenPanel>

      {isLoading ? (
        <SkeletonList count={4} />
      ) : ladeFehler && !auftraege ? (
        <FehlerZustand fehler={ladeFehler} was="Die Aufträge" onErneut={() => void neuLaden()} />
      ) : !auftraege || auftraege.length === 0 ? (
        <EmptyState
          icon={Layers}
          text="Noch kein Auftrag angelegt. Aufträge bündeln Vorgänge eines Gewerks oder Projekts."
          action={
            darfAnlegen ? (
              <button type="button" onClick={() => setZeigeNeuerAuftrag(true)} className="btn-ap px-4 py-2 text-sekundaer">
                Neuer Auftrag
              </button>
            ) : undefined
          }
        />
      ) : gefiltert.length === 0 ? (
        <EmptyState icon={Search} text="Kein Auftrag entspricht der Suche." />
      ) : (
        <AuftraegeTabelle auftraege={gefiltert} onZeileKlick={setAusgewaehlterAuftrag} />
      )}

      {ausgewaehlterAuftrag && (
        <AuftragDetailPanel auftrag={ausgewaehlterAuftrag} onClose={() => setAusgewaehlterAuftrag(null)} />
      )}
    </div>
  );
}
