import { useQuery } from "@tanstack/react-query";
import { Gauge, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { pruefmittelApi, usersApi } from "../../api/endpoints";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import { FilterChip } from "../../components/apple/FilterChip";
import { SearchField } from "../../components/apple/SearchField";
import { useAuth } from "../../context/AuthContext";
import type { Pruefmittel } from "../../types";
import { heuteIso } from "../../utils/format";
import {
  BALD_FAELLIG_TAGE,
  FAELLIGKEIT_LABEL,
  FAELLIGKEIT_TONE,
  PRUEFMITTEL_STATUS_LABEL,
  faelligkeitsStufe,
  filterePruefmittel,
  type PruefmittelFaelligFilter,
} from "../../utils/pruefmittel";
import { ListeMitPanel } from "../ListeMitPanel";
import { SeitenKopf } from "../OfficeUi";
import { SortierbareTabelle, type Spalte } from "../SortierbareTabelle";
import { PruefmittelAnlegenFormular } from "./PruefmittelAnlegenFormular";
import { PruefmittelDetail } from "./PruefmittelDetail";

const FAELLIG_FILTER: { wert: PruefmittelFaelligFilter; label: string }[] = [
  { wert: "alle", label: "Alle" },
  { wert: "ueberfaellig", label: "Überfällig" },
  { wert: "bald", label: `Fällig in ${BALD_FAELLIG_TAGE} Tagen` },
  { wert: "ok", label: "In Ordnung" },
];

/** Desktop-Fassung der Prüfmittelverwaltung: Tabelle links, Detailpanel rechts.
 * Auswahl steckt in der URL (/pruefmittel/:id). Die Feld-App behält ihre Kartenliste. */
export function OfficePruefmittelPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentUser, hatRecht } = useAuth();
  const [suche, setSuche] = useState("");
  const [faellig, setFaellig] = useState<PruefmittelFaelligFilter>("alle");
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
  const gefiltert = filterePruefmittel(data ?? [], suche, faellig, heute, bald, nameFuer);
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
        <SearchField
          value={suche}
          onChange={setSuche}
          placeholder="Bezeichnung, Seriennummer, Nutzer…"
          ariaLabel="Prüfmittel suchen"
          className="w-72"
        />
        <button onClick={() => setNeu(true)} className="btn-ap-primary flex items-center gap-1.5 px-3 py-1.5 text-sekundaer font-semibold">
          <Plus size={14} strokeWidth={2.5} />
          Neues Prüfmittel
        </button>
      </SeitenKopf>

      <div className="mb-4 flex flex-wrap gap-2">
        {FAELLIG_FILTER.map((f) => (
          <FilterChip key={f.wert} label={f.label} aktiv={faellig === f.wert} onClick={() => setFaellig(f.wert)} />
        ))}
      </div>

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
            <EmptyState icon={Search} text="Kein Prüfmittel entspricht der Suche oder dem Filter." />
          ) : (
            <SortierbareTabelle
              zeilen={gefiltert}
              spalten={sichtbareSpalten}
              zeilenKey={(p) => p.id}
              gewaehlt={id}
              onWaehlen={(p) => navigate(`/pruefmittel/${p.id}`)}
              startSortierung={{ key: "faellig" }}
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
