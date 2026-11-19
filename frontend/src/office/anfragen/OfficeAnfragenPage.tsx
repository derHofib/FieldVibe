import { useQuery } from "@tanstack/react-query";
import { ClipboardList, Inbox, MessageSquarePlus, Search, UserPlus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { kundenApi, vorgangAnfragenApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { IconBadge, type IconTone } from "../../components/IconBadge";
import { StatusPille } from "../../components/apple/StatusPille";
import { filterAnwenden, sucheAnwenden } from "../../components/filter/auswerten";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import { useFilterZustand } from "../../components/filter/useFilterZustand";
import { SkeletonList } from "../../components/Skeleton";
import { useAuth } from "../../context/AuthContext";
import {
  LEISTUNGSTYP_LABEL,
  eingangRelativ,
  nurDatum,
  useAnfragenFilterFelder,
} from "../../pages/feld/anfragen/anfragenGemeinsam";
import type { VorgangAnfrage } from "../../types";
import { ListeMitPanel } from "../ListeMitPanel";
import { Karte, SeitenKopf } from "../OfficeUi";
import { SortierbareTabelle, type Spalte } from "../SortierbareTabelle";
import { AnfragePanel } from "./AnfragePanel";
import { ANFRAGE_STATUS_PILLE } from "./statusPille";

const DREI_TAGE_MS = 3 * 86_400_000;
const PANEL_ALLEIN = "(max-width: 1279px)";

/** Unter 1280 px bleibt neben dem Panel keine brauchbare Tabellenbreite. */
function useNurPanelBreite(): boolean {
  const [schmal, setSchmal] = useState(() => (typeof window.matchMedia === "function" ? window.matchMedia(PANEL_ALLEIN).matches : false));
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(PANEL_ALLEIN);
    const onChange = () => setSchmal(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return schmal;
}

const ersteZeile = (text: string | null) => (text ?? "").split("\n").find((z) => z.trim() !== "") ?? "";
const standortAnlage = (a: VorgangAnfrage) => `${a.standort_bezeichnung ?? ""} ${a.anlage_bezeichnung ?? ""}`;

const SCHRITTE: { icon: typeof Inbox; tone: IconTone; titel: string; text: string }[] = [
  { icon: UserPlus, tone: "sky", titel: "Zugang anlegen", text: "Beim Kunden unter Kommunikation › Kundenportal einen Zugang einrichten." },
  { icon: MessageSquarePlus, tone: "amber", titel: "Kunde fragt an", text: "Der Kunde wählt Standort, Anlage und Art und beschreibt sein Anliegen." },
  { icon: ClipboardList, tone: "emerald", titel: "Annehmen", text: "Hier mit Abrechnungsart und Priorität annehmen, daraus wird ein Vorgang." },
];

function LeerFlaeche({ kundenLink }: { kundenLink: boolean }) {
  return (
    <Karte className="px-6 py-10">
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-2 text-center">
        <span className="flex h-11 w-11 items-center justify-center rounded-full bg-fill text-label2">
          <Inbox size={20} strokeWidth={2} aria-hidden="true" />
        </span>
        <h2 className="text-zeile font-semibold text-label">Noch keine Anfragen</h2>
        <p className="max-w-lg text-sekundaer text-label2">
          Kunden mit Portal-Zugang können im Kundenportal Anfragen stellen. Neue Anfragen erscheinen hier und als Mitteilung in der Glocke.
        </p>
        <ol className="mt-4 grid w-full gap-3 text-left sm:grid-cols-3">
          {SCHRITTE.map((s, i) => (
            <li key={s.titel} className="flex items-start gap-3 rounded-[var(--radius-ap-card)] bg-fill p-3">
              <IconBadge icon={s.icon} tone={s.tone} />
              <div>
                <p className="text-fliess font-semibold text-label">
                  {i + 1}. {s.titel}
                </p>
                <p className="mt-0.5 text-sekundaer text-label2">{s.text}</p>
              </div>
            </li>
          ))}
        </ol>
        {kundenLink && (
          <Link to="/kunden" className="btn-ap mt-4 px-4 py-2 text-sekundaer">
            Zu den Kunden
          </Link>
        )}
      </div>
    </Karte>
  );
}

/** Desktop-Fassung der Vorgangsanfragen: Tabelle über die volle Breite, Auswahl
 * (/anfragen/:id) öffnet rechts das Detailpanel. */
export function OfficeAnfragenPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { hatRecht } = useAuth();
  const nurPanel = useNurPanelBreite();
  const query = params.toString() ? `?${params.toString()}` : "";

  const { data: anfragen, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["vorgang-anfragen"],
    queryFn: () => vorgangAnfragenApi.list(),
  });
  const { data: kunden } = useQuery({
    queryKey: ["kunden"],
    queryFn: () => kundenApi.list(),
    enabled: hatRecht("kunden", "sehen"),
  });

  const felder = useAnfragenFilterFelder(kunden);
  const zustand = useFilterZustand({ felder });

  // Wie bisher: ohne gespeicherten Filterstand in der URL nur offene Anfragen zeigen.
  const startFilterGesetzt = useRef(false);
  useEffect(() => {
    if (startFilterGesetzt.current) return;
    startFilterGesetzt.current = true;
    if (!params.has("f")) zustand.setBedingungen([{ feld: "status", op: "ist", wert: ["offen"] }]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sichtbar = sucheAnwenden(
    filterAnwenden(anfragen ?? [], zustand.bedingungen, felder),
    zustand.sucheVerzoegert,
    (a) => `${a.titel} ${a.beschreibung ?? ""} ${a.kunde_name ?? ""}`,
  );

  const alleSpalten: Spalte<VorgangAnfrage>[] = [
    {
      key: "eingegangen",
      label: "Eingegangen",
      render: (a) => {
        const ueberfaellig = a.status === "offen" && Date.now() - new Date(a.created_at).getTime() > DREI_TAGE_MS;
        return (
          <span className="block whitespace-nowrap font-normal">
            <span className="block text-label">{nurDatum(a.created_at)}</span>
            <span className={`block text-sekundaer ${ueberfaellig ? "font-semibold text-st-arbeit" : "text-label2"}`}>
              {eingangRelativ(a.created_at)}
            </span>
          </span>
        );
      },
      sortWert: (a) => a.created_at,
    },
    {
      key: "titel",
      label: "Anfrage",
      haupt: true,
      render: (a) => (
        <span className="block max-w-[18rem]">
          <span className="block truncate font-semibold" title={a.titel}>
            {a.titel}
          </span>
          <span className="block truncate text-sekundaer font-normal text-label2">{ersteZeile(a.beschreibung)}</span>
        </span>
      ),
      sortWert: (a) => a.titel,
    },
    {
      key: "kunde",
      label: "Kunde",
      render: (a) => (
        <span className="block max-w-[14rem] truncate" title={a.kunde_name ?? undefined}>
          {a.kunde_name ?? "–"}
        </span>
      ),
      sortWert: (a) => a.kunde_name ?? "" },
    {
      key: "standort",
      label: "Standort · Anlage",
      render: (a) =>
        a.standort_bezeichnung && a.anlage_bezeichnung ? (
          <span className="block">
            <span className="block">{a.standort_bezeichnung}</span>
            <span className="block text-sekundaer text-label2">{a.anlage_bezeichnung}</span>
          </span>
        ) : (
          <span className="block">{a.standort_bezeichnung || a.anlage_bezeichnung || "–"}</span>
        ),
      sortWert: standortAnlage,
    },
    {
      key: "leistungstyp",
      label: "Art",
      render: (a) => (
        <span className="inline-block whitespace-nowrap rounded-[var(--radius-ap-pill)] border border-sep px-2 py-0.5 text-meta text-label">
          {LEISTUNGSTYP_LABEL[a.leistungstyp]}
        </span>
      ),
      sortWert: (a) => LEISTUNGSTYP_LABEL[a.leistungstyp],
    },
    { key: "gestellt_von", label: "Gestellt von", render: (a) => a.gestellt_von_name ?? "–", sortWert: (a) => a.gestellt_von_name ?? "" },
    {
      key: "status",
      label: "Status",
      render: (a) => <StatusPille status={ANFRAGE_STATUS_PILLE[a.status].ton} label={ANFRAGE_STATUS_PILLE[a.status].label} />,
      sortWert: (a) => a.status,
    },
  ];
  const spalten = id ? alleSpalten.filter((s) => s.key !== "gestellt_von" && s.key !== "standort") : alleSpalten;

  const gewaehlt = id ? anfragen?.find((a) => a.id === id) : undefined;
  const panel = !id ? null : gewaehlt ? (
    <AnfragePanel key={gewaehlt.id} anfrage={gewaehlt} alle={anfragen ?? []} />
  ) : isLoading ? (
    <SkeletonList count={3} />
  ) : (
    <FehlerZustand fehler={ladeFehler ?? new ApiError(404, "nicht gefunden")} was="Die Anfrage" onErneut={() => void neuLaden()} />
  );

  const gesamtLeer = !!anfragen && anfragen.length === 0;

  return (
    <div>
      <SeitenKopf titel="Vorgangsanfragen" anzahl={isLoading || (ladeFehler && !anfragen) ? undefined : sichtbar.length} />

      {!gesamtLeer && <FilterLeiste felder={felder} zustand={zustand} variante="office" suchPlatzhalter="Anfragen durchsuchen…" className="mb-4" />}

      <ListeMitPanel
        panelTitel="Anfrage"
        panel={panel}
        nurPanel={nurPanel}
        onSchliessen={() => id && navigate(`/anfragen${query}`)}
        liste={
          isLoading ? (
            <SkeletonList count={6} />
          ) : ladeFehler && !anfragen ? (
            <FehlerZustand fehler={ladeFehler} was="Die Anfragen" onErneut={() => void neuLaden()} />
          ) : gesamtLeer || !anfragen ? (
            <LeerFlaeche kundenLink={hatRecht("kunden", "sehen")} />
          ) : sichtbar.length === 0 ? (
            <EmptyState
              icon={Search}
              text={
                zustand.sucheVerzoegert && zustand.bedingungen.length === 0
                  ? `Nichts gefunden für „${zustand.sucheVerzoegert}“`
                  : "Keine Treffer für diese Filter"
              }
              action={
                <button type="button" onClick={zustand.zuruecksetzen} className="btn-ap px-4 py-2 text-sekundaer">
                  Filter zurücksetzen
                </button>
              }
            />
          ) : (
            <SortierbareTabelle
              zeilen={sichtbar}
              spalten={spalten}
              zeilenKey={(a) => a.id}
              gewaehlt={id}
              onWaehlen={(a) => navigate(`/anfragen/${a.id}${query}`)}
              startSortierung={{ key: "eingegangen", absteigend: true }}
              hervorgehoben={zustand.bedingungen.map((b) => b.feld)}
            />
          )
        }
      />
    </div>
  );
}
