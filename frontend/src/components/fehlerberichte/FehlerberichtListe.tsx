import { useQuery } from "@tanstack/react-query";
import { Building2, Bug, CalendarDays, Copy, Gauge, Image as BildIcon, Lightbulb } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { fehlerberichteApi, mandantenApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import type { FehlerberichtListItem, FehlerberichtZaehler } from "../../types";
import { EmptyState } from "../EmptyState";
import { FehlerZustand } from "../FehlerZustand";
import { datumZuVonBis } from "../../utils/datumFilterParameter";
import { FilterLeiste } from "../filter/FilterLeiste";
import type { FilterFeld } from "../filter/typen";
import { useFilterZustand } from "../filter/useFilterZustand";
import { SegmentedControl } from "../apple/SegmentedControl";
import { STATUS_KREIS_KLASSE } from "../apple/status";
import { FehlerStatusPille, SchweregradBadge } from "./Badges";
import {
  FEHLER_STATUS,
  FEHLER_STATUS_TOKEN,
  OFFENE_STATUS,
  SCHWEREGRADE,
  SCHWEREGRAD_LABEL,
  istDringend,
  relativeZeit,
  statusLabel,
} from "./darstellung";
import { ladeBerichte, type ArtReiter, type ListenFilter, type StatusFilter } from "./liste";
import { SkeletonList } from "../Skeleton";

function offenAnzahl(z: FehlerberichtZaehler): number {
  return OFFENE_STATUS.reduce((summe, s) => summe + z[s], 0);
}

function Kachel({
  label,
  anzahl,
  aktiv,
  punktKlasse,
  onClick,
}: {
  label: string;
  anzahl: number | undefined;
  aktiv: boolean;
  punktKlasse?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={aktiv}
      onClick={onClick}
      className={`flex flex-col items-start gap-1 rounded-[var(--radius-ap-card)] p-3 text-left transition-colors ${
        aktiv ? "bg-tint-solid text-white" : "bg-cell text-label hover:bg-fill"
      }`}
    >
      <span className="text-titel-mobil font-bold leading-none tabular-nums">{anzahl ?? "–"}</span>
      <span className="flex items-center gap-1.5 text-sekundaer font-semibold">
        {punktKlasse && (
          <span
            className={`h-2 w-2 shrink-0 rounded-full ${aktiv ? "bg-white" : `bg-current ${punktKlasse}`}`}
            aria-hidden="true"
          />
        )}
        {label}
      </span>
    </button>
  );
}

const REITER: { wert: ArtReiter; label: string }[] = [
  { wert: "fehler", label: "Fehler" },
  { wert: "idee", label: "Ideen" },
  { wert: "alle", label: "Alle" },
];

function leseReiter(wert: string | null): ArtReiter {
  return wert === "idee" || wert === "alle" ? wert : "fehler";
}

function Zeile({ b, zeigeMandant, detailPfad }: { b: FehlerberichtListItem; zeigeMandant: boolean; detailPfad: (id: string) => string }) {
  const dringend = istDringend(b.schweregrad);
  const meta = [zeigeMandant ? b.mandant_name : null, b.melder_name].filter(Boolean).join(" · ");
  return (
    <li data-dringend={dringend} className="relative">
      {dringend && (
        <span
          aria-hidden="true"
          className={`absolute top-2 bottom-2 left-0 w-1 rounded-r-full ${
            b.schweregrad === "blockierend" ? "bg-st-fehlt-dot" : "bg-st-arbeit-dot"
          }`}
        />
      )}
      <Link to={detailPfad(b.id)} className="flex flex-col gap-1.5 px-4 py-3 hover:bg-fill">
        <div className="flex items-start justify-between gap-3">
          <p className={`flex min-w-0 items-start gap-2 text-fliess text-label ${dringend ? "font-bold" : "font-semibold"}`}>
            {b.art === "idee" ? (
              <Lightbulb size={16} strokeWidth={2} className="mt-0.5 shrink-0 text-tone-amber" aria-label="Idee" role="img" />
            ) : (
              <Bug size={16} strokeWidth={2} className="mt-0.5 shrink-0 text-label2" aria-label="Fehler" role="img" />
            )}
            <span className="min-w-0">{b.titel}</span>
          </p>
          <span className="shrink-0 text-meta text-label2" title={new Date(b.created_at).toLocaleString("de-DE")}>
            {relativeZeit(b.created_at)}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <SchweregradBadge schweregrad={b.schweregrad} />
          <FehlerStatusPille status={b.status} art={b.art} />
          {b.duplikat_von_id && (
            <span className="inline-flex items-center gap-1 text-sekundaer text-label2">
              <Copy size={12} strokeWidth={2} aria-hidden="true" />
              Mögliches Duplikat
            </span>
          )}
          {b.hat_screenshot && (
            <span className="inline-flex items-center text-label2" title="Mit Screenshot">
              <BildIcon size={14} strokeWidth={2} aria-hidden="true" />
              <span className="sr-only">Mit Screenshot</span>
            </span>
          )}
        </div>
        {(meta || b.route) && (
          <p className="truncate text-sekundaer text-label2">
            {meta}
            {meta && b.route ? " · " : ""}
            {b.route && <span className="font-mono">{b.route}</span>}
          </p>
        )}
      </Link>
    </li>
  );
}

/** Liste mit Zaehler-Kacheln und Filtern -- Super-Admin (mit Mandantenfilter)
 * und Office (ohne) teilen sich diese Komponente. */
export function FehlerberichtListe({
  mitMandantFilter,
  detailPfad,
}: {
  mitMandantFilter: boolean;
  detailPfad: (id: string) => string;
}) {
  const { isImpersonating } = useAuth();
  // Der Reiter steckt in der URL (?art=), damit Zurück aus dem Detail ihn behält.
  const [suchParameter, setSuchParameter] = useSearchParams();
  const art = leseReiter(suchParameter.get("art"));
  const [status, setStatus] = useState<StatusFilter>("offen");
  const reiterWaehlen = (neu: ArtReiter) => {
    setSuchParameter(
      (alt) => {
        const naechste = new URLSearchParams(alt);
        if (neu === "fehler") naechste.delete("art");
        else naechste.set("art", neu);
        return naechste;
      },
      { replace: true },
    );
    setStatus("offen");
  };
  const artFilter = art === "alle" ? undefined : art;
  const textArt = art === "idee" ? "idee" : "fehler";

  const { data: mandanten } = useQuery({
    queryKey: ["mandanten"],
    queryFn: mandantenApi.list,
    enabled: mitMandantFilter && !isImpersonating,
  });

  const felder = useMemo<FilterFeld<unknown>[]>(
    () => [
      {
        key: "schweregrad",
        label: art === "idee" ? "Priorität" : "Schweregrad",
        typ: "auswahl",
        icon: Gauge,
        operatoren: ["ist"],
        einzelwert: true,
        optionen: SCHWEREGRADE.map((s) => ({ wert: s, label: SCHWEREGRAD_LABEL[s] })),
      },
      ...(mitMandantFilter
        ? [
            {
              key: "mandant",
              label: "Mandant",
              typ: "verknuepfung" as const,
              icon: Building2,
              operatoren: ["ist" as const],
              einzelwert: true,
              optionen: (mandanten ?? []).map((m) => ({ wert: m.id, label: m.name })),
            },
          ]
        : []),
      // Das Backend kennt nur eine Untergrenze (`seit`), daher kein "vor"/"zwischen".
      { key: "gemeldet", label: "Gemeldet", typ: "datum", icon: CalendarDays, operatoren: ["nach", "relativ"] },
    ],
    [art, mitMandantFilter, mandanten],
  );
  const zustand = useFilterZustand({ felder });
  const erster = (key: string) => {
    const w = zustand.bedingungen.find((b) => b.feld === key)?.wert;
    return Array.isArray(w) ? w[0] : "";
  };
  const gemeldet = zustand.bedingungen.find((b) => b.feld === "gemeldet");
  const von = gemeldet ? datumZuVonBis(gemeldet).von : undefined;
  const filter: ListenFilter = {
    art,
    status,
    schweregrad: erster("schweregrad") as ListenFilter["schweregrad"],
    mandantId: mitMandantFilter ? erster("mandant") : "",
    q: zustand.sucheVerzoegert,
    seit: von ? new Date(`${von}T00:00:00`).toISOString() : "",
  };
  const mandantId = filter.mandantId;
  const { data: zaehler } = useQuery({
    queryKey: ["fehlerberichte", "zaehler", mandantId, art],
    queryFn: () => fehlerberichteApi.zaehler(mandantId || undefined, artFilter),
  });
  const abfrageFilter = filter;
  const { data: berichte, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["fehlerberichte", "liste", abfrageFilter],
    queryFn: () => ladeBerichte(abfrageFilter),
  });

  // Erneuter Klick auf die aktive Kachel kehrt zum Standard "offen" zurueck.
  const kachelKlick = (neu: StatusFilter) => setStatus(status === neu ? "offen" : neu);
  const filterAktiv = zustand.bedingungen.length > 0 || zustand.sucheVerzoegert !== "";

  return (
    <div className="space-y-4">
      <SegmentedControl<ArtReiter> ariaLabel="Art" wert={art} onChange={reiterWaehlen} optionen={REITER} />
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
        <Kachel
          label="Offen"
          anzahl={zaehler && offenAnzahl(zaehler)}
          aktiv={status === "offen"}
          onClick={() => kachelKlick("offen")}
        />
        {FEHLER_STATUS.map((s) => (
          <Kachel
            key={s}
            label={statusLabel(s, textArt)}
            anzahl={zaehler?.[s]}
            punktKlasse={STATUS_KREIS_KLASSE[FEHLER_STATUS_TOKEN[s]]}
            aktiv={status === s}
            onClick={() => kachelKlick(s)}
          />
        ))}
        <Kachel
          label="Alle"
          anzahl={zaehler?.gesamt}
          aktiv={status === "alle"}
          onClick={() => kachelKlick("alle")}
        />
      </div>

      <FilterLeiste
        felder={felder}
        zustand={zustand}
        variante="office"
        suchPlatzhalter="Titel oder Beschreibung"
      />

      {isLoading ? (
        <SkeletonList count={4} />
      ) : ladeFehler && !berichte ? (
        <FehlerZustand fehler={ladeFehler} was="Die Meldungen" onErneut={() => void neuLaden()} />
      ) : berichte && berichte.length > 0 ? (
        <ul className="divide-y divide-sep overflow-hidden rounded-[var(--radius-ap-card)] bg-cell">
          {berichte.map((b) => (
            <Zeile key={b.id} b={b} zeigeMandant={mitMandantFilter} detailPfad={detailPfad} />
          ))}
        </ul>
      ) : (
        <EmptyState
          icon={art === "idee" ? Lightbulb : Bug}
          text={
            filterAktiv
              ? zustand.bedingungen.length > 0 || !zustand.sucheVerzoegert
                ? "Keine Treffer für diese Filter"
                : `Nichts gefunden für „${zustand.sucheVerzoegert}"`
              : art === "idee"
                ? "Keine Ideen für diese Auswahl."
                : art === "alle"
                  ? "Keine Meldungen für diese Auswahl."
                  : "Keine Fehlerberichte für diese Auswahl."
          }
          action={
            filterAktiv ? (
              <button type="button" onClick={zustand.zuruecksetzen} className="btn-ap px-3 py-1.5 text-sekundaer">
                Filter zurücksetzen
              </button>
            ) : undefined
          }
        />
      )}
    </div>
  );
}
