import { useQuery } from "@tanstack/react-query";
import { Bug, Copy, Image as BildIcon } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { fehlerberichteApi, mandantenApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import type { FehlerberichtListItem, FehlerberichtSchweregrad, FehlerberichtZaehler } from "../../types";
import { EmptyState } from "../EmptyState";
import { SearchField } from "../apple/SearchField";
import { STATUS_KREIS_KLASSE } from "../apple/status";
import { FehlerStatusPille, SchweregradBadge } from "./Badges";
import {
  FEHLER_STATUS,
  FEHLER_STATUS_LABEL,
  FEHLER_STATUS_TOKEN,
  OFFENE_STATUS,
  SCHWEREGRADE,
  SCHWEREGRAD_LABEL,
  istDringend,
  relativeZeit,
} from "./darstellung";
import { STANDARD_FILTER, ladeBerichte, type ListenFilter, type StatusFilter, type Zeitraum } from "./liste";

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
          <p className={`min-w-0 text-[15px] text-label ${dringend ? "font-bold" : "font-semibold"}`}>{b.titel}</p>
          <span className="shrink-0 text-xs text-label2" title={new Date(b.created_at).toLocaleString("de-DE")}>
            {relativeZeit(b.created_at)}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <SchweregradBadge schweregrad={b.schweregrad} />
          <FehlerStatusPille status={b.status} />
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
  const [filter, setFilter] = useState<ListenFilter>(STANDARD_FILTER);
  const setze = (teil: Partial<ListenFilter>) => setFilter((f) => ({ ...f, ...teil }));

  const { data: mandanten } = useQuery({
    queryKey: ["mandanten"],
    queryFn: mandantenApi.list,
    enabled: mitMandantFilter && !isImpersonating,
  });
  const mandantId = mitMandantFilter ? filter.mandantId : "";
  const { data: zaehler } = useQuery({
    queryKey: ["fehlerberichte", "zaehler", mandantId],
    queryFn: () => fehlerberichteApi.zaehler(mandantId || undefined),
  });
  const { data: berichte, isLoading, isError } = useQuery({
    queryKey: ["fehlerberichte", "liste", { ...filter, mandantId }],
    queryFn: () => ladeBerichte({ ...filter, mandantId }),
  });

  // Erneuter Klick auf die aktive Kachel kehrt zum Standard "offen" zurueck.
  const kachelKlick = (status: StatusFilter) => setze({ status: filter.status === status ? "offen" : status });
  const abweichend =
    filter.status !== "offen" || filter.schweregrad || filter.mandantId || filter.q || filter.zeitraum;

  return (
    <div className="space-y-4">
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
            label={FEHLER_STATUS_LABEL[s]}
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
          ariaLabel="Fehlerberichte durchsuchen"
          className="sm:col-span-2 lg:col-span-1"
        />
        <select
          aria-label="Schweregrad"
          value={filter.schweregrad}
          onChange={(e) => setze({ schweregrad: e.target.value as FehlerberichtSchweregrad | "" })}
          className="field-ap"
        >
          <option value="">Alle Schweregrade</option>
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
        <p className="text-st-fehlt">Fehlerberichte konnten nicht geladen werden.</p>
      ) : berichte && berichte.length > 0 ? (
        <ul className="divide-y divide-sep overflow-hidden rounded-[var(--radius-ap-card)] bg-cell">
          {berichte.map((b) => (
            <Zeile key={b.id} b={b} zeigeMandant={mitMandantFilter} detailPfad={detailPfad} />
          ))}
        </ul>
      ) : (
        <EmptyState icon={Bug} text="Keine Fehlerberichte für diese Auswahl." />
      )}
    </div>
  );
}
