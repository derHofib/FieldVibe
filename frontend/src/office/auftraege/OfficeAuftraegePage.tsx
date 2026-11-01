import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Layers, Plus } from "lucide-react";
import { useState } from "react";

import { auftraegeApi, kundenApi, projekteApi } from "../../api/endpoints";
import { SearchableSelect } from "../../components/SearchableSelect";
import { EmptyState } from "../../components/EmptyState";
import type { Auftrag } from "../../types";
import { Karte, SeitenKopf } from "../OfficeUi";
import { AuftraegeTabelle } from "./AuftraegeTabelle";
import { AuftragDetailPanel } from "./AuftragDetailPanel";

/** Tabellen-Ansicht aller Auftraege (Projekt->Auftrag->Vorgang, siehe
 * app/models/auftrag.py) -- analog zu OfficeVorgaengePage.tsx, aber ohne
 * die dortigen Ansichts-Umschalter (Liste/Kanban/Raster): bei der
 * erwarteten Auftrags-Anzahl reicht eine einzelne Tabelle. */
export function OfficeAuftraegePage() {
  const queryClient = useQueryClient();
  const [zeigeNeuerAuftrag, setZeigeNeuerAuftrag] = useState(false);
  const [neuerTitel, setNeuerTitel] = useState("");
  const [neuerProjektId, setNeuerProjektId] = useState("");
  const [neuerKundeId, setNeuerKundeId] = useState("");
  const [ausgewaehlterAuftrag, setAusgewaehlterAuftrag] = useState<Auftrag | null>(null);

  const { data: auftraege, isLoading } = useQuery({
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
        <button onClick={() => setZeigeNeuerAuftrag(true)} className="btn-ap-primary">
          <Plus size={14} strokeWidth={2.5} aria-hidden="true" />
          Neuer Auftrag
        </button>
      </SeitenKopf>

      {zeigeNeuerAuftrag && (
        <Karte className="mb-4 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[220px] flex-1">
              <label className="mb-1 block text-xs font-medium text-label2">Titel</label>
              <input
                autoFocus
                value={neuerTitel}
                onChange={(e) => setNeuerTitel(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && neuerTitel.trim() && auftragErstellen.mutate()}
                placeholder="z. B. Elektro-Gewerk Sanierung Musterstraße"
                className="field-ap"
              />
            </div>
            <div className="min-w-[200px] flex-1">
              <label className="mb-1 block text-xs font-medium text-label2">Projekt (optional)</label>
              <SearchableSelect
                value={neuerProjektId}
                onChange={setNeuerProjektId}
                placeholder="Kein Projekt"
                options={(projekte ?? []).map((p) => ({ value: p.id, label: p.name }))}
              />
            </div>
            <div className="min-w-[200px] flex-1">
              <label className="mb-1 block text-xs font-medium text-label2">Kunde (optional)</label>
              <SearchableSelect
                value={neuerKundeId}
                onChange={setNeuerKundeId}
                placeholder="Kein Kunde"
                options={(kunden ?? []).map((k) => ({ value: k.id, label: k.name }))}
              />
            </div>
            <button
              onClick={() => auftragErstellen.mutate()}
              disabled={!neuerTitel.trim() || auftragErstellen.isPending}
              className="btn-ap-primary"
            >
              Anlegen
            </button>
            <button onClick={() => setZeigeNeuerAuftrag(false)} className="btn-ap">
              Abbrechen
            </button>
          </div>
        </Karte>
      )}

      {isLoading ? (
        <p className="py-10 text-center text-sm text-label2">Lädt…</p>
      ) : !auftraege || auftraege.length === 0 ? (
        <EmptyState icon={Layers} text="Noch kein Auftrag angelegt." />
      ) : (
        <AuftraegeTabelle auftraege={auftraege} onZeileKlick={setAusgewaehlterAuftrag} />
      )}

      {ausgewaehlterAuftrag && (
        <AuftragDetailPanel auftrag={ausgewaehlterAuftrag} onClose={() => setAusgewaehlterAuftrag(null)} />
      )}
    </div>
  );
}
