import { useQuery } from "@tanstack/react-query";
import { Bug, Copy, Image as BildIcon, Lightbulb } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { fehlerberichteApi, mandantenApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import type { FehlerberichtListItem, FehlerberichtSchweregrad, FehlerberichtZaehler } from "../../types";
import { EmptyState } from "../EmptyState";
import { SearchField } from "../apple/SearchField";
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
import { STANDARD_FILTER, ladeBerichte, type ArtReiter, type ListenFilter, type StatusFilter, type Zeitraum } from "./liste";

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
      <span className="text-[22px] font-bold leading-none tabular-nums">{anzahl ?? "–"}</span>
      <span className="flex items-center gap-1.5 text-xs font-semibold">
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
          <p className={`flex min-w-0 items-start gap-2 text-[15px] text-label ${dringend ? "font-bold" : "font-semibold"}`}>
            {b.art === "idee" ? (
              <Lightbulb size={16} strokeWidth={2} className="mt-0.5 shrink-0 text-tone-amber" aria-label="Idee" role="img" />
            ) : (
              <Bug size={16} strokeWidth={2} className="mt-0.5 shrink-0 text-label2" aria-label="Fehler" role="img" />
            )}
            <span className="min-w-0">{b.titel}</span>
          </p>
          <span className="shrink-0 text-xs text-label2" title={new Date(b.created_at).toLocaleString("de-DE")}>
            {relativeZeit(b.created_at)}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <SchweregradBadge schweregrad={b.schweregrad} />
          <FehlerStatusPille status={b.status} art={b.art} />
          {b.duplikat_von_id && (
            <span className="inline-flex items-center gap-1 text-xs text-label2">
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
          <p className="truncate text-xs text-label2">
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
  const [lokal, setFilter] = useState<Omit<ListenFilter, "art">>(STANDARD_FILTER);
  const filter: ListenFilter = { ...lokal, art };
  const setze = (teil: Partial<Omit<ListenFilter, "art">>) => setFilter((f) => ({ ...f, ...teil }));
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
    setFilter((f) => ({ ...f, status: "offen" }));
  };
  const artFilter = art === "alle" ? undefined : art;
  const textArt = art === "idee" ? "idee" : "fehler";

  const { data: mandanten } = useQuery({
    queryKey: ["mandanten"],
    queryFn: mandantenApi.list,
    enabled: mitMandantFilter && !isImpersonating,
  });
  const mandantId = mitMandantFilter ? filter.mandantId : "";
  const { data: zaehler } = useQuery({
    queryKey: ["fehlerberichte", "zaehler", mandantId, art],
    queryFn: () => fehlerberichteApi.zaehler(mandantId || undefined, artFilter),
  });
  const { data: berichte, isLoading, isError } = useQuery({
    queryKey: ["fehlerberichte", "liste", { ...filter, mandantId }],
    queryFn: () => ladeBerichte({ ...filter, mandantId }),
  });

  // Erneuter Klick auf die aktive Kachel kehrt zum Standard "offen" zurueck.
  const kachelKlick = (status: StatusFilter) => setze({ status: filter.status === status ? "offen" : status });
  const abweichend = lokal.status !== "offen" || lokal.schweregrad || lokal.mandantId || lokal.q || lokal.zeitraum;

  return (
    <div className="space-y-4">
      <SegmentedControl<ArtReiter> ariaLabel="Art" wert={art} onChange={reiterWaehlen} optionen={REITER} />
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
        <Kachel
          label="Offen"
          anzahl={zaehler && offenAnzahl(zaehler)}
          aktiv={filter.status === "offen"}
          onClick={() => kachelKlick("offen")}
        />
        {FEHLER_STATUS.map((s) => (
          <Kachel
            key={s}
            label={statusLabel(s, textArt)}
            anzahl={zaehler?.[s]}
            punktKlasse={STATUS_KREIS_KLASSE[FEHLER_STATUS_TOKEN[s]]}
            aktiv={filter.status === s}
            onClick={() => kachelKlick(s)}
          />
        ))}
        <Kachel
          label="Alle"
          anzahl={zaehler?.gesamt}
          aktiv={filter.status === "alle"}
          onClick={() => kachelKlick("alle")}
        />
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <SearchField
          value={filter.q}
          onChange={(q) => setze({ q })}
          placeholder="Titel oder Beschreibung"
          ariaLabel={art === "idee" ? "Ideen durchsuchen" : art === "alle" ? "Fehler und Ideen durchsuchen" : "Fehlerberichte durchsuchen"}
          className="sm:col-span-2 lg:col-span-1"
        />
        <select
          aria-label="Schweregrad"
          value={filter.schweregrad}
          onChange={(e) => setze({ schweregrad: e.target.value as FehlerberichtSchweregrad | "" })}
          className="field-ap"
        >
          <option value="">{art === "idee" ? "Alle Prioritäten" : "Alle Schweregrade"}</option>
          {SCHWEREGRADE.map((s) => (
            <option key={s} value={s}>
              {SCHWEREGRAD_LABEL[s]}
            </option>
          ))}
        </select>
        <select
          aria-label="Zeitraum"
          value={filter.zeitraum}
          onChange={(e) => setze({ zeitraum: e.target.value as Zeitraum })}
          className="field-ap"
        >
          <option value="">Gesamter Zeitraum</option>
          <option value="24h">Letzte 24 Stunden</option>
          <option value="7d">Letzte 7 Tage</option>
          <option value="30d">Letzte 30 Tage</option>
        </select>
        {mitMandantFilter && (
          <select
            aria-label="Mandant"
            value={filter.mandantId}
            onChange={(e) => setze({ mandantId: e.target.value })}
            className="field-ap"
          >
            <option value="">Alle Mandanten</option>
            {mandanten?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        )}
      </div>
      {abweichend && (
        <button type="button" onClick={() => setFilter(STANDARD_FILTER)} className="text-sm font-medium text-tint-text">
          Filter zurücksetzen
        </button>
      )}

      {isLoading ? (
        <p className="text-label2">Lädt…</p>
      ) : isError ? (
        <p className="text-st-fehlt">Meldungen konnten nicht geladen werden.</p>
      ) : berichte && berichte.length > 0 ? (
        <ul className="divide-y divide-sep overflow-hidden rounded-[var(--radius-ap-card)] bg-cell">
          {berichte.map((b) => (
            <Zeile key={b.id} b={b} zeigeMandant={mitMandantFilter} detailPfad={detailPfad} />
          ))}
        </ul>
      ) : (
        <EmptyState
          icon={art === "idee" ? Lightbulb : Bug}
          text={art === "idee" ? "Keine Ideen für diese Auswahl." : art === "alle" ? "Keine Meldungen für diese Auswahl." : "Keine Fehlerberichte für diese Auswahl."}
        />
      )}
    </div>
  );
}
