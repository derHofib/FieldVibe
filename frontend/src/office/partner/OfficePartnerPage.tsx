import { useQuery } from "@tanstack/react-query";
import { CircleDot, HardHat, MapPin, Phone, Plus, Search, User, Wrench } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { partnerApi } from "../../api/endpoints";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { filterAnwenden, sucheAnwenden } from "../../components/filter/auswerten";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import type { FilterFeld } from "../../components/filter/typen";
import { useFilterZustand } from "../../components/filter/useFilterZustand";
import { PartnerAnlegenFormular } from "../../components/PartnerAnlegenFormular";
import { SkeletonList } from "../../components/Skeleton";
import { useAuth } from "../../context/AuthContext";
import { PartnerProfilePage } from "../../pages/feld/PartnerProfilePage";
import type { Partner } from "../../types";
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

const KONTAKTE = (p: Partner) => p.ansprechpartner.map((a) => a.name).join(", ");

// Schlüssel = Spalten-Key, damit SortierbareTabelle den Kopf hervorheben kann.
const FELDER: FilterFeld<Partner>[] = [
  { key: "name", label: "Name", typ: "text", icon: HardHat, wert: (p) => p.name },
  { key: "gewerk", label: "Gewerk", typ: "text", icon: Wrench, wert: (p) => p.gewerk },
  { key: "kontakt", label: "Ansprechpartner", typ: "text", icon: User, wert: KONTAKTE },
  { key: "telefon", label: "Telefon", typ: "text", icon: Phone, wert: (p) => p.telefon },
  { key: "ort", label: "Ort", typ: "text", icon: MapPin, wert: ORT },
  {
    key: "status",
    label: "Status",
    typ: "auswahl",
    icon: CircleDot,
    wert: (p) => (p.aktiv ? "aktiv" : "inaktiv"),
    optionen: [
      { wert: "aktiv", label: "Aktiv" },
      { wert: "inaktiv", label: "Inaktiv" },
    ],
  },
];

const suchtext = (p: Partner) =>
  [p.name, p.gewerk, p.email, p.telefon, ORT(p), KONTAKTE(p), p.aktiv ? "aktiv" : "inaktiv"].join(" ");

/** Desktop-Fassung der Partnerliste: Tabelle links, das bestehende
 * Partnerprofil als Detailpanel rechts. Die Auswahl steckt in der URL
 * (/partner/:id), damit Reload und Deep-Links sie behalten. */
export function OfficePartnerPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentUser, hatRecht } = useAuth();
  const zustand = useFilterZustand({ felder: FELDER });
  const [params] = useSearchParams();
  const startGesetzt = useRef(false);
  const [neu, setNeu] = useState(false);

  const kannSehen = istModulAktiv(currentUser, "nachunternehmer") && hatRecht("partner", "sehen");
  const kannAnlegen = hatRecht("partner", "erstellen");

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["partner"],
    queryFn: () => partnerApi.list(),
    enabled: kannSehen,
  });

  // Bisher war "aktiv" voreingestellt: ohne `f` in der URL einmalig als Start-Bedingung setzen.
  const ohneFilterInUrl = !params.has("f");
  const { setBedingungen } = zustand;
  useEffect(() => {
    if (startGesetzt.current) return;
    startGesetzt.current = true;
    if (ohneFilterInUrl) setBedingungen([{ feld: "status", op: "ist", wert: ["aktiv"] }]);
  }, [ohneFilterInUrl, setBedingungen]);

  if (!kannSehen) {
    return <EmptyState icon={HardHat} text="Kein Zugriff auf Partner und Nachunternehmer." />;
  }

  const gefiltert = sucheAnwenden(
    filterAnwenden(data ?? [], zustand.bedingungen, FELDER),
    zustand.sucheVerzoegert,
    suchtext,
  );
  const panel = id ? <PartnerProfilePage key={id} id={id} eingebettet /> : null;

  return (
    <div>
      <SeitenKopf titel="Partner & Nachunternehmer" anzahl={isLoading || isError ? undefined : gefiltert.length}>
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

      <FilterLeiste felder={FELDER} zustand={zustand} variante="office" suchPlatzhalter="Partner suchen…" className="mb-4" />

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
              // Bei offenem Panel ist die Tabelle schmal -- Nebenspalten weglassen statt abschneiden
              spalten={id ? SPALTEN.filter((s) => !["kontakt", "telefon", "email"].includes(s.key)) : SPALTEN}
              zeilenKey={(p) => p.id}
              gewaehlt={id}
              onWaehlen={(p) => navigate(`/partner/${p.id}`)}
              startSortierung={{ key: "name" }}
              hervorgehoben={zustand.bedingungen.map((b) => b.feld)}
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
