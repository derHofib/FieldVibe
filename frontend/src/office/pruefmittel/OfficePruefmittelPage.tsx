import { useQuery } from "@tanstack/react-query";
import { CalendarCheck, CalendarClock, CircleDot, Gauge, Hash, Plus, Search, TriangleAlert, User } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { pruefmittelApi, usersApi } from "../../api/endpoints";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { filterAnwenden, sucheAnwenden } from "../../components/filter/auswerten";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import type { FilterFeld } from "../../components/filter/typen";
import { useFilterZustand } from "../../components/filter/useFilterZustand";
import { SkeletonList } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import { useAuth } from "../../context/AuthContext";
import type { Pruefmittel } from "../../types";
import { heuteIso } from "../../utils/format";
import {
  BALD_FAELLIG_TAGE,
  FAELLIGKEIT_LABEL,
  FAELLIGKEIT_TONE,
  PRUEFMITTEL_STATUS_LABEL,
  faelligkeitsStufe,
} from "../../utils/pruefmittel";
import { ListeMitPanel } from "../ListeMitPanel";
import { SeitenKopf } from "../OfficeUi";
import { SortierbareTabelle, type Spalte } from "../SortierbareTabelle";
import { PruefmittelAnlegenFormular } from "./PruefmittelAnlegenFormular";
import { PruefmittelDetail } from "./PruefmittelDetail";

/** Desktop-Fassung der Prüfmittelverwaltung: Tabelle links, Detailpanel rechts.
 * Auswahl steckt in der URL (/pruefmittel/:id). Die Feld-App behält ihre Kartenliste. */
export function OfficePruefmittelPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentUser, hatRecht } = useAuth();
  const [neu, setNeu] = useState(false);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["pruefmittel"],
    queryFn: () => pruefmittelApi.list(),
  });
  const { data: users } = useQuery({
    queryKey: ["users", "auswahl"],
    queryFn: usersApi.auswahl,
    enabled: hatRecht("mitarbeiterverwaltung", "sehen"),
  });
  const nutzer = useMemo(() => (users ?? []).filter((u) => u.aktiv), [users]);
  const nameFuer = (userId: string | null) => users?.find((u) => u.id === userId)?.name ?? "";

  const heute = heuteIso();
  const bald = heuteIso(BALD_FAELLIG_TAGE);

  // Defekte/ausgemusterte Geräte werden nicht kalibriert: sie haben keine Fälligkeit statt "überfällig".
  const stufeWert = (p: Pruefmittel) =>
    p.status === "aktiv" ? faelligkeitsStufe(p.naechste_kalibrierung_am, heute, bald) : null;
  const felder = useMemo<FilterFeld<Pruefmittel>[]>(
    () => [
      { key: "bezeichnung", label: "Bezeichnung", typ: "text", icon: Gauge, wert: (p) => p.bezeichnung },
      { key: "sn", label: "Seriennummer", typ: "text", icon: Hash, wert: (p) => p.seriennummer },
      {
        key: "nutzer",
        label: "Zugewiesen an",
        typ: "person",
        icon: User,
        wert: (p) => p.zugewiesen_an,
        optionen: nutzer.map((u) => ({ wert: u.id, label: u.name })),
      },
      { key: "letzte", label: "Letzte Kalibrierung", typ: "datum", icon: CalendarCheck, wert: (p) => p.letzte_kalibrierung_am },
      { key: "faellig", label: "Nächste Kalibrierung", typ: "datum", icon: CalendarClock, wert: (p) => p.naechste_kalibrierung_am },
      {
        key: "faelligkeit",
        label: "Fälligkeit",
        typ: "auswahl",
        icon: TriangleAlert,
        wert: stufeWert,
        optionen: [
          { wert: "ueberfaellig", label: FAELLIGKEIT_LABEL.ueberfaellig },
          { wert: "bald", label: `Bald fällig (${BALD_FAELLIG_TAGE} Tage)` },
          { wert: "ok", label: FAELLIGKEIT_LABEL.ok },
        ],
      },
      {
        key: "status",
        label: "Status",
        typ: "auswahl",
        icon: CircleDot,
        wert: (p) => p.status,
        optionen: Object.entries(PRUEFMITTEL_STATUS_LABEL).map(([wert, label]) => ({ wert, label })),
      },
    ],
    [nutzer, heute, bald],
  );
  const zustand = useFilterZustand({ felder });
  const gefiltert = sucheAnwenden(
    filterAnwenden(data ?? [], zustand.bedingungen, felder),
    zustand.sucheVerzoegert,
    (p) => [p.bezeichnung, p.seriennummer, nameFuer(p.zugewiesen_an), PRUEFMITTEL_STATUS_LABEL[p.status]].join(" "),
  );
  const gewaehlt = id ? (data ?? []).find((p) => p.id === id) : undefined;

  const spalten: Spalte<Pruefmittel>[] = [
    { key: "bezeichnung", label: "Bezeichnung", haupt: true, render: (p) => p.bezeichnung, sortWert: (p) => p.bezeichnung },
    { key: "sn", label: "Seriennummer", render: (p) => p.seriennummer ?? "–", sortWert: (p) => p.seriennummer ?? "" },
    { key: "nutzer", label: "Zugewiesen an", render: (p) => nameFuer(p.zugewiesen_an) || "–", sortWert: (p) => nameFuer(p.zugewiesen_an) },
    {
      key: "letzte",
      label: "Letzte Kalibrierung",
      render: (p) => (p.letzte_kalibrierung_am ? new Date(p.letzte_kalibrierung_am).toLocaleDateString("de-DE") : "–"),
      sortWert: (p) => p.letzte_kalibrierung_am ?? "",
    },
    {
      key: "faellig",
      label: "Nächste Kalibrierung",
      render: (p) => {
        const stufe = faelligkeitsStufe(p.naechste_kalibrierung_am, heute, bald);
        return (
          <span className="flex items-center gap-2 whitespace-nowrap">
            {new Date(p.naechste_kalibrierung_am).toLocaleDateString("de-DE")}
            {p.status === "aktiv" && stufe !== "ok" && <StatusBadge label={FAELLIGKEIT_LABEL[stufe]} tone={FAELLIGKEIT_TONE[stufe]} />}
          </span>
        );
      },
      sortWert: (p) => p.naechste_kalibrierung_am,
    },
    {
      key: "status",
      label: "Status",
      render: (p) => <StatusBadge label={PRUEFMITTEL_STATUS_LABEL[p.status]} tone={p.status === "aktiv" ? "emerald" : "rose"} />,
      sortWert: (p) => PRUEFMITTEL_STATUS_LABEL[p.status],
    },
  ];
  // Bei offenem Panel ist die Tabelle schmal -- Nebenspalten weglassen statt abschneiden
  const sichtbareSpalten = id ? spalten.filter((s) => !["sn", "letzte", "nutzer"].includes(s.key)) : spalten;

  return (
    <div>
      <SeitenKopf titel="Prüfmittel" anzahl={isLoading || isError ? undefined : gefiltert.length}>
        <button onClick={() => setNeu(true)} className="btn-ap-primary flex items-center gap-1.5 px-3 py-1.5 text-sekundaer font-semibold">
          <Plus size={14} strokeWidth={2.5} />
          Neues Prüfmittel
        </button>
      </SeitenKopf>

      <FilterLeiste felder={felder} zustand={zustand} variante="office" suchPlatzhalter="Prüfmittel suchen…" className="mb-4" />

      <ListeMitPanel
        panelTitel="Prüfmittel"
        panel={
          id ? (
            gewaehlt ? (
              <PruefmittelDetail
                key={gewaehlt.id}
                mittel={gewaehlt}
                nutzer={nutzer}
                kannLoeschen={currentUser?.role === "loesch_operativ"}
                onGeloescht={() => navigate("/pruefmittel")}
              />
            ) : (
              <EmptyState icon={Gauge} text={isLoading ? "Lädt…" : "Prüfmittel nicht gefunden."} />
            )
          ) : null
        }
        onSchliessen={() => id && navigate("/pruefmittel")}
        liste={
          isLoading ? (
            <SkeletonList count={6} />
          ) : isError ? (
            <FehlerZustand fehler={error} was="Die Prüfmittel" onErneut={() => void refetch()} />
          ) : (data ?? []).length === 0 ? (
            <EmptyState
              icon={Gauge}
              text="Noch keine Prüfmittel erfasst."
              action={
                <button type="button" onClick={() => setNeu(true)} className="btn-ap px-4 py-2 text-sekundaer">
                  Neues Prüfmittel
                </button>
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
            <SortierbareTabelle
              zeilen={gefiltert}
              spalten={sichtbareSpalten}
              zeilenKey={(p) => p.id}
              gewaehlt={id}
              onWaehlen={(p) => navigate(`/pruefmittel/${p.id}`)}
              startSortierung={{ key: "faellig" }}
              hervorgehoben={zustand.bedingungen.map((b) => (b.feld === "faelligkeit" ? "faellig" : b.feld))}
            />
          )
        }
      />

      <AnlegenPanel offen={neu} onClose={() => setNeu(false)} titel="Neues Prüfmittel">
        <PruefmittelAnlegenFormular
          nutzer={nutzer}
          onAngelegt={(p) => {
            setNeu(false);
            navigate(`/pruefmittel/${p.id}`);
          }}
        />
      </AnlegenPanel>
    </div>
  );
}
