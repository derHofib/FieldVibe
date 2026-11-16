import { useQuery } from "@tanstack/react-query";
import { HardHat, Plus, Search } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { partnerApi } from "../../api/endpoints";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { PartnerAnlegenFormular } from "../../components/PartnerAnlegenFormular";
import { SkeletonList } from "../../components/Skeleton";
import { FilterChip } from "../../components/apple/FilterChip";
import { SearchField } from "../../components/apple/SearchField";
import { useAuth } from "../../context/AuthContext";
import { PartnerProfilePage } from "../../pages/feld/PartnerProfilePage";
import type { Partner } from "../../types";
import { filterePartner, type PartnerStatusFilter } from "../../utils/geschaeft";
import { istModulAktiv } from "../../utils/module";
import { ListeMitPanel } from "../ListeMitPanel";
import { SeitenKopf } from "../OfficeUi";
import { SortierbareTabelle, type Spalte } from "../SortierbareTabelle";

const ORT = (p: Partner) => [p.adresse?.plz, p.adresse?.ort].filter(Boolean).join(" ");

const SPALTEN: Spalte<Partner>[] = [
  { key: "name", label: "Name", haupt: true, render: (p) => p.name, sortWert: (p) => p.name },
  { key: "gewerk", label: "Gewerk", render: (p) => p.gewerk ?? "–", sortWert: (p) => p.gewerk ?? "" },
  {
    key: "kontakt",
    label: "Ansprechpartner",
    render: (p) =>
      p.ansprechpartner.length === 0
        ? "–"
        : `${p.ansprechpartner[0].name}${p.ansprechpartner.length > 1 ? ` +${p.ansprechpartner.length - 1}` : ""}`,
    sortWert: (p) => p.ansprechpartner[0]?.name ?? "",
  },
  {
    key: "telefon",
    label: "Telefon",
    render: (p) =>
      p.telefon ? (
        <a href={`tel:${p.telefon}`} onClick={(e) => e.stopPropagation()} className="whitespace-nowrap text-tint hover:underline">
          {p.telefon}
        </a>
      ) : (
        "–"
      ),
  },
  {
    key: "email",
    label: "E-Mail",
    render: (p) =>
      p.email ? (
        <a href={`mailto:${p.email}`} onClick={(e) => e.stopPropagation()} className="text-tint hover:underline">
          {p.email}
        </a>
      ) : (
        "–"
      ),
  },
  { key: "ort", label: "Ort", render: (p) => <span className="whitespace-nowrap">{ORT(p) || "–"}</span>, sortWert: ORT },
  {
    key: "status",
    label: "Status",
    render: (p) =>
      p.aktiv ? (
        ""
      ) : (
        <span className="rounded-[var(--radius-ap-pill)] bg-fill px-2 py-0.5 text-meta font-semibold text-label2">inaktiv</span>
      ),
    sortWert: (p) => (p.aktiv ? 0 : 1),
  },
];

const STATUS_FILTER: { wert: PartnerStatusFilter; label: string }[] = [
  { wert: "aktiv", label: "Aktiv" },
  { wert: "inaktiv", label: "Inaktiv" },
  { wert: "alle", label: "Alle" },
];

/** Desktop-Fassung der Partnerliste: Tabelle links, das bestehende
 * Partnerprofil als Detailpanel rechts. Die Auswahl steckt in der URL
 * (/partner/:id), damit Reload und Deep-Links sie behalten. */
export function OfficePartnerPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentUser, hatRecht } = useAuth();
  const [suche, setSuche] = useState("");
  const [status, setStatus] = useState<PartnerStatusFilter>("aktiv");
  const [neu, setNeu] = useState(false);

  const kannSehen = istModulAktiv(currentUser, "nachunternehmer") && hatRecht("partner", "sehen");
  const kannAnlegen = hatRecht("partner", "erstellen");

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["partner"],
    queryFn: () => partnerApi.list(),
    enabled: kannSehen,
  });

  if (!kannSehen) {
    return <EmptyState icon={HardHat} text="Kein Zugriff auf Partner und Nachunternehmer." />;
  }

  const gefiltert = filterePartner(data ?? [], suche, status);
  const panel = id ? <PartnerProfilePage key={id} id={id} eingebettet /> : null;

  return (
    <div>
      <SeitenKopf titel="Partner & Nachunternehmer" anzahl={isLoading || isError ? undefined : gefiltert.length}>
        <SearchField
          value={suche}
          onChange={setSuche}
          placeholder="Name, Gewerk, Ort, Ansprechpartner…"
          ariaLabel="Partner suchen"
          className="w-72"
        />
        {kannAnlegen && (
          <button
            onClick={() => setNeu(true)}
            className="btn-ap-primary flex items-center gap-1.5 px-3 py-1.5 text-sekundaer font-semibold"
          >
            <Plus size={14} strokeWidth={2.5} />
            Neuer Partner
          </button>
        )}
      </SeitenKopf>

      <div className="mb-4 flex flex-wrap gap-2">
        {STATUS_FILTER.map((f) => (
          <FilterChip key={f.wert} label={f.label} aktiv={status === f.wert} onClick={() => setStatus(f.wert)} />
        ))}
      </div>

      <ListeMitPanel
        panelTitel="Partnerprofil"
        panel={panel}
        onSchliessen={() => id && navigate("/partner")}
        liste={
          isLoading ? (
            <SkeletonList count={6} />
          ) : isError ? (
            <FehlerZustand fehler={error} was="Die Partner" onErneut={() => void refetch()} />
          ) : (data ?? []).length === 0 ? (
            <EmptyState
              icon={HardHat}
              text="Noch keine Partner/Nachunternehmer angelegt."
              action={
                kannAnlegen ? (
                  <button type="button" onClick={() => setNeu(true)} className="btn-ap px-4 py-2 text-sekundaer">
                    Neuer Partner
                  </button>
                ) : undefined
              }
            />
          ) : gefiltert.length === 0 ? (
            <EmptyState icon={Search} text="Kein Partner entspricht der Suche oder dem Filter." />
          ) : (
            <SortierbareTabelle
              zeilen={gefiltert}
              // Bei offenem Panel ist die Tabelle schmal -- Nebenspalten weglassen statt abschneiden
              spalten={id ? SPALTEN.filter((s) => !["kontakt", "telefon", "email"].includes(s.key)) : SPALTEN}
              zeilenKey={(p) => p.id}
              gewaehlt={id}
              onWaehlen={(p) => navigate(`/partner/${p.id}`)}
              startSortierung={{ key: "name" }}
            />
          )
        }
      />

      <AnlegenPanel offen={neu} onClose={() => setNeu(false)} titel="Neuer Partner">
        <PartnerAnlegenFormular
          onAngelegt={(p) => {
            setNeu(false);
            navigate(`/partner/${p.id}`);
          }}
        />
      </AnlegenPanel>
    </div>
  );
}
