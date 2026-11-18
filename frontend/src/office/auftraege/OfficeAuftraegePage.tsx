import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, CircleDot, FolderKanban, Hash, Layers, Plus, Search, Users } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { auftraegeApi, kundenApi, projekteApi } from "../../api/endpoints";
import { SearchableSelect } from "../../components/SearchableSelect";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { EmptyState } from "../../components/EmptyState";
import { filterAnwenden, sucheAnwenden } from "../../components/filter/auswerten";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import type { FilterFeld } from "../../components/filter/typen";
import { useFilterZustand } from "../../components/filter/useFilterZustand";
import { NEU_BUTTON_KLASSE } from "../../components/FormularFeld";
import { useAuth } from "../../context/AuthContext";
import type { Auftrag } from "../../types";
import { SeitenKopf } from "../OfficeUi";
import { AUFTRAG_STATUS_LABEL, AuftraegeTabelle } from "./AuftraegeTabelle";
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
  const [zeigeNeuerAuftrag, setZeigeNeuerAuftrag] = useState(false);
  const [neuerTitel, setNeuerTitel] = useState("");
  const [neuerProjektId, setNeuerProjektId] = useState("");
  const [neuerKundeId, setNeuerKundeId] = useState("");
  const [ausgewaehlterAuftrag, setAusgewaehlterAuftrag] = useState<Auftrag | null>(null);

  const { data: auftraege, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["auftraege"],
    queryFn: () => auftraegeApi.list(),
  });

  // Deep-Links: ?auftrag=<id> oeffnet das Panel (Links aus Pfad/Herkunft/Projekt-Ansicht),
  // ?neu=1&projekt_id=<id> das Anlegen mit vorbelegtem Projekt. Einmal verbrauchen, damit Schliessen
  // wirkt; Filter (`f`/`q`) stehen in derselben URL und bleiben.
  const [suchParams, setSuchParams] = useSearchParams();
  useEffect(() => {
    const auftragId = suchParams.get("auftrag");
    const neu = suchParams.get("neu") === "1";
    if (!auftragId && !neu) return;
    if (auftragId) {
      if (!auftraege) return;
      const treffer = auftraege.find((a) => a.id === auftragId);
      if (treffer) setAusgewaehlterAuftrag(treffer);
    }
    if (neu) {
      setNeuerProjektId(suchParams.get("projekt_id") ?? "");
      setZeigeNeuerAuftrag(true);
    }
    setSuchParams(
      (prev) => {
        const n = new URLSearchParams(prev);
        n.delete("auftrag");
        n.delete("neu");
        n.delete("projekt_id");
        return n;
      },
      { replace: true },
    );
  }, [suchParams, auftraege, setSuchParams]);

  const { data: projekte } = useQuery({
    queryKey: ["projekte"],
    queryFn: () => projekteApi.list(),
  });

  const { data: kunden } = useQuery({
    queryKey: ["kunden"],
    queryFn: () => kundenApi.list(),
    enabled: zeigeNeuerAuftrag,
  });

  // Schlüssel = Spalten-Id der Tabelle (Kopf-Hervorhebung).
  const felder = useMemo<FilterFeld<Auftrag>[]>(() => {
    // Kunden aus den Aufträgen selbst: braucht kein Recht auf die Kundenliste und listet nur relevante Kunden.
    const kundenOptionen = new Map<string, string>();
    for (const a of auftraege ?? []) if (a.kunde_id && a.kunde_name) kundenOptionen.set(a.kunde_id, a.kunde_name);
    return [
      { key: "titel", label: "Titel", typ: "text", icon: Layers, wert: (a) => a.titel },
      {
        key: "kunde",
        label: "Kunde",
        typ: "verknuepfung",
        icon: Users,
        wert: (a) => a.kunde_id,
        optionen: [...kundenOptionen].map(([wert, label]) => ({ wert, label })),
      },
      {
        key: "projekt",
        label: "Projekt",
        typ: "verknuepfung",
        icon: FolderKanban,
        wert: (a) => a.projekt_id,
        optionen: (projekte ?? []).map((p) => ({ wert: p.id, label: p.name })),
      },
      {
        key: "status",
        label: "Status",
        typ: "auswahl",
        icon: CircleDot,
        wert: (a) => a.status,
        optionen: Object.entries(AUFTRAG_STATUS_LABEL).map(([wert, label]) => ({ wert, label })),
      },
      { key: "vorgaenge_gesamt", label: "Vorgänge", typ: "zahl", icon: Hash, wert: (a) => a.vorgaenge_gesamt },
      { key: "created_at", label: "Erstellt am", typ: "datum", icon: CalendarDays, wert: (a) => a.created_at },
    ];
  }, [auftraege, projekte]);
  const zustand = useFilterZustand({ felder });
  const projektNamen = useMemo(() => new Map((projekte ?? []).map((p) => [p.id, p.name])), [projekte]);

  // Die Liste wird vollständig geladen, daher genügt ein Client-Filter.
  const gefiltert = useMemo(
    () =>
      sucheAnwenden(
        filterAnwenden(auftraege ?? [], zustand.bedingungen, felder),
        zustand.sucheVerzoegert,
        (a) => [a.titel, a.kunde_name, a.projekt_name, AUFTRAG_STATUS_LABEL[a.status]].join(" "),
      ),
    [auftraege, zustand.bedingungen, zustand.sucheVerzoegert, felder],
  );

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
      <SeitenKopf titel="Aufträge" anzahl={isLoading || !auftraege ? undefined : gefiltert.length}>
        {darfAnlegen && (
          <button onClick={() => setZeigeNeuerAuftrag(true)} className={NEU_BUTTON_KLASSE}>
            <Plus size={14} strokeWidth={2.5} aria-hidden="true" />
            Neuer Auftrag
          </button>
        )}
      </SeitenKopf>

      <FilterLeiste felder={felder} zustand={zustand} variante="office" suchPlatzhalter="Aufträge suchen…" className="mb-4" />

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
        <EmptyState
          icon={Search}
          text={zustand.sucheVerzoegert && zustand.bedingungen.length === 0 ? `Nichts gefunden für „${zustand.sucheVerzoegert}“` : "Keine Treffer für diese Filter"}
          action={
            <button type="button" onClick={zustand.zuruecksetzen} className="btn-ap px-4 py-2 text-sekundaer">
              Filter zurücksetzen
            </button>
          }
        />
      ) : (
        <AuftraegeTabelle
          auftraege={gefiltert}
          onZeileKlick={setAusgewaehlterAuftrag}
          hervorgehoben={zustand.bedingungen.map((b) => b.feld)}
          projektNamen={projektNamen}
        />
      )}

      {ausgewaehlterAuftrag && (
        <AuftragDetailPanel auftrag={ausgewaehlterAuftrag} onClose={() => setAusgewaehlterAuftrag(null)} />
      )}
    </div>
  );
}
