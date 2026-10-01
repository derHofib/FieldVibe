import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Package, Search, Unlink } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../../api/client";
import { partnerApi, zeitplanApi } from "../../../api/endpoints";
import { SearchableSelect } from "../../../components/SearchableSelect";
import { GroupedList, GroupedListRow, GroupedListValueRow } from "../../../components/apple/GroupedList";
import { Sheet } from "../../../components/apple/Sheet";
import { StatusPille } from "../../../components/apple/StatusPille";
import { VORGANG_STATUS_LABEL, vorgangStatusZuToken } from "../../../components/apple/status";
import type { ZeitplanBestellungRef, ZeitplanElement, ZeitplanElementUpdate, ZeitplanVorgangRef } from "../../../types";
import { formatKurz, parseTag, terminLabel } from "./zeitplanLogik";

const TYP_TITEL = { phase: "Phase", schritt: "Schritt", meilenstein: "Meilenstein" } as const;
const BESTELLUNG_STATUS_LABEL = { entwurf: "Entwurf", bestellt: "Bestellt", eingegangen: "Eingegangen" } as const;

function Abschnitt({ titel, children }: { titel: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="px-1 text-[13px] font-semibold tracking-wide text-label2 uppercase">{titel}</h3>
      {children}
    </section>
  );
}

function useVerzoegert(wert: string, ms = 250): string {
  const [v, setV] = useState(wert);
  useEffect(() => {
    const t = window.setTimeout(() => setV(wert), ms);
    return () => window.clearTimeout(t);
  }, [wert, ms]);
  return v;
}

function Suchfeld({ wert, onChange, label }: { wert: string; onChange: (v: string) => void; label: string }) {
  return (
    <div className="relative">
      <Search size={15} strokeWidth={2} className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-label3" aria-hidden="true" />
      <input
        type="search"
        value={wert}
        onChange={(e) => onChange(e.target.value)}
        placeholder={label}
        aria-label={label}
        className="field-ap !pl-8"
      />
    </div>
  );
}

function LoesenKnopf({ onClick, label, disabled }: { onClick: () => void; label: string; disabled: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex h-8 shrink-0 items-center gap-1 rounded-[8px] px-2 text-[13px] font-medium text-st-fehlt hover:bg-st-fehlt-bg disabled:opacity-50"
    >
      <Unlink size={14} strokeWidth={2} aria-hidden="true" />
      {label}
    </button>
  );
}

function VorgangVerknuepfung({
  projektId,
  element,
  busy,
  onPatch,
  onClose,
}: {
  projektId: string;
  element: ZeitplanElement;
  busy: boolean;
  onPatch: (body: ZeitplanElementUpdate) => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const qv = useVerzoegert(q.trim());
  const { data, isFetching } = useQuery({
    queryKey: ["zeitplan-auswahl-vorgaenge", projektId, qv],
    queryFn: () => zeitplanApi.auswahlVorgaenge(projektId, qv),
    enabled: !element.vorgang,
  });

  if (element.vorgang) {
    const v: ZeitplanVorgangRef = element.vorgang;
    return (
      <div className="space-y-2">
        <div className="card-ap flex items-center gap-2 p-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-[15px] text-label">
              <span className="font-semibold tabular-nums">{v.vorgangsnummer}</span> · {v.titel}
            </p>
            <div className="mt-1 flex items-center gap-2">
              <StatusPille status={vorgangStatusZuToken(v.status)} label={VORGANG_STATUS_LABEL[v.status]} />
              <Link
                to={`/vorgaenge/${v.id}/vollbild`}
                onClick={onClose}
                className="inline-flex items-center gap-1 text-[13px] font-medium text-tint-text hover:underline"
              >
                Vorgang öffnen <ExternalLink size={12} strokeWidth={2} aria-hidden="true" />
              </Link>
            </div>
          </div>
          <LoesenKnopf label="Lösen" disabled={busy} onClick={() => onPatch({ vorgang_id: null })} />
        </div>
        {element.termine.length > 0 && (
          <ul className="space-y-0.5 px-1 text-[13px] text-label2">
            {element.termine.map((t) => (
              <li key={t.id}>{terminLabel(t)}</li>
            ))}
          </ul>
        )}
        <p className="px-1 text-xs text-label2">Wird der Vorgang abgeschlossen, gilt der Schritt automatisch als erledigt.</p>
      </div>
    );
  }

  const eigene = (data ?? []).filter((v) => v.gehoert_zum_projekt);
  const weitere = (data ?? []).filter((v) => !v.gehoert_zum_projekt);
  const zeile = (v: (typeof eigene)[number], letzte: boolean) => (
    <GroupedListRow key={v.id} onClick={() => !busy && onPatch({ vorgang_id: v.id })} last={letzte}>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[15px] text-label">
          <span className="font-semibold tabular-nums">{v.vorgangsnummer}</span> · {v.titel}
        </p>
      </div>
      <StatusPille status={vorgangStatusZuToken(v.status)} label={VORGANG_STATUS_LABEL[v.status]} />
    </GroupedListRow>
  );

  return (
    <div className="space-y-2">
      <Suchfeld wert={q} onChange={setQ} label="Vorgang suchen (Nummer oder Titel)" />
      <div className="max-h-64 space-y-2 overflow-y-auto">
        {eigene.length > 0 && (
          <div>
            <p className="px-1 pb-1 text-xs font-semibold text-label2">Aus diesem Projekt</p>
            <GroupedList>{eigene.map((v, i) => zeile(v, i === eigene.length - 1))}</GroupedList>
          </div>
        )}
        {weitere.length > 0 && (
          <div>
            <p className="px-1 pb-1 text-xs font-semibold text-label2">{eigene.length > 0 ? "Weitere Vorgänge" : "Vorgänge"}</p>
            <GroupedList>{weitere.map((v, i) => zeile(v, i === weitere.length - 1))}</GroupedList>
          </div>
        )}
        {data && data.length === 0 && <p className="px-1 text-sm text-label2">Keine Vorgänge gefunden.</p>}
        {!data && isFetching && <p className="px-1 text-sm text-label2">Suche läuft …</p>}
      </div>
    </div>
  );
}

function liefertermin(b: ZeitplanBestellungRef): string {
  return b.liefertermin ? `Liefertermin ${formatKurz(parseTag(b.liefertermin))}` : "Liefertermin offen";
}

function BestellungVerknuepfung({
  projektId,
  element,
  busy,
  onPatch,
  onClose,
}: {
  projektId: string;
  element: ZeitplanElement;
  busy: boolean;
  onPatch: (body: ZeitplanElementUpdate) => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const qv = useVerzoegert(q.trim());
  const { data, isFetching, error } = useQuery({
    queryKey: ["zeitplan-auswahl-bestellungen", projektId, qv],
    queryFn: () => zeitplanApi.auswahlBestellungen(projektId, qv),
    enabled: !element.bestellung,
    // Fehlendes Recht (Modul Material) aendert sich beim Wiederholen nicht.
    retry: (n, e) => !(e instanceof ApiError && e.status === 403) && n < 2,
  });
  const keinRecht = error instanceof ApiError && error.status === 403;

  if (element.bestellung) {
    const b = element.bestellung;
    return (
      <div className="space-y-2">
        <div className="card-ap flex items-center gap-2 p-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-[15px] text-label">
              <span className="font-semibold tabular-nums">{b.bestellnummer}</span>
              {b.lieferant_name ? ` · ${b.lieferant_name}` : ""}
            </p>
            <p className={`text-[13px] ${b.liefertermin ? "text-label2" : "text-st-arbeit"}`}>
              {liefertermin(b)} · {BESTELLUNG_STATUS_LABEL[b.status]}
            </p>
            <Link
              to={`/bestellungen/${b.id}`}
              onClick={onClose}
              className="mt-0.5 inline-flex items-center gap-1 text-[13px] font-medium text-tint-text hover:underline"
            >
              Bestellung öffnen <ExternalLink size={12} strokeWidth={2} aria-hidden="true" />
            </Link>
          </div>
          <LoesenKnopf label="Lösen" disabled={busy} onClick={() => onPatch({ bestellung_id: null })} />
        </div>
        <p className="px-1 text-xs text-label2">
          Das Datum dieses Meilensteins kommt aus dem Liefertermin der Bestellung und kann hier nicht verschoben werden. Änderungen am Liefertermin
          erfolgen in der Bestellung.
        </p>
      </div>
    );
  }

  if (keinRecht) {
    return (
      <p className="rounded-[10px] bg-fill px-3 py-2 text-sm text-label2">
        Für die Auswahl von Bestellungen fehlt dir der Zugriff auf das Modul Material (Recht „Material sehen“). Bitte wende dich an einen
        Administrator.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <Suchfeld wert={q} onChange={setQ} label="Bestellung suchen (Nummer oder Lieferant)" />
      <div className="max-h-64 overflow-y-auto">
        {data && data.length > 0 && (
          <GroupedList>
            {data.map((b, i) => (
              <GroupedListRow key={b.id} onClick={() => !busy && onPatch({ bestellung_id: b.id })} last={i === data.length - 1}>
                <Package size={16} strokeWidth={2} className="shrink-0 text-label2" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[15px] text-label">
                    <span className="font-semibold tabular-nums">{b.bestellnummer}</span>
                    {b.lieferant_name ? ` · ${b.lieferant_name}` : ""}
                  </p>
                  <p className={`text-xs ${b.liefertermin ? "text-label2" : "text-st-arbeit"}`}>{liefertermin(b)}</p>
                </div>
              </GroupedListRow>
            ))}
          </GroupedList>
        )}
        {data && data.length === 0 && <p className="px-1 text-sm text-label2">Keine Bestellungen gefunden.</p>}
        {error && !keinRecht && <p role="alert" className="px-1 text-sm text-st-fehlt">Bestellungen konnten nicht geladen werden.</p>}
        {!data && isFetching && <p className="px-1 text-sm text-label2">Suche läuft …</p>}
      </div>
    </div>
  );
}

function PartnerAuswahl({ element, busy, onPatch }: { element: ZeitplanElement; busy: boolean; onPatch: (body: ZeitplanElementUpdate) => void }) {
  const { data: partner } = useQuery({ queryKey: ["partner"], queryFn: () => partnerApi.list() });
  const optionen = (partner ?? []).filter((p) => p.aktiv || p.id === element.partner?.id).map((p) => ({ value: p.id, label: p.name, sublabel: p.gewerk ?? undefined }));
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <SearchableSelect
          className="flex-1"
          value={element.partner?.id ?? ""}
          onChange={(id) => id && id !== element.partner?.id && !busy && onPatch({ partner_id: id })}
          placeholder="Kein Fremdgewerk"
          options={optionen}
        />
        {element.partner && <LoesenKnopf label="Lösen" disabled={busy} onClick={() => onPatch({ partner_id: null })} />}
      </div>
      <p className="px-1 text-xs text-label2">Der Schritt wird im Plan als Fremdgewerk dargestellt und erscheint im Partnerportal des Nachunternehmers.</p>
    </div>
  );
}

/** Detail-Sheet eines Zeitplan-Elements: Kopfdaten und je Typ die
 * Verknuepfungen (Vorgang/Fremdgewerk beim Schritt, Bestellung beim
 * Meilenstein). Der Aufrufer reicht immer das aktuelle Element aus dem
 * Query-Cache herein, die Anzeige folgt damit dem Server-Stand. */
export function ElementDetailSheet({
  projektId,
  element,
  zeitraumText,
  fehler,
  busy,
  onPatch,
  onClose,
}: {
  projektId: string;
  element: ZeitplanElement;
  zeitraumText: string;
  fehler: string | null;
  busy: boolean;
  onPatch: (body: ZeitplanElementUpdate) => void;
  onClose: () => void;
}) {
  return (
    <Sheet
      offen
      onClose={onClose}
      titel={`${TYP_TITEL[element.typ]}-Details`}
      rechts={
        <button type="button" onClick={onClose} className="text-[17px] font-semibold text-tint-text">
          Fertig
        </button>
      }
    >
      <div className="space-y-5 p-4">
        <div>
          <h3 className="text-[20px] leading-tight font-bold text-label">{element.titel}</h3>
          <p className="text-[13px] text-label2">{TYP_TITEL[element.typ]}</p>
        </div>

        <GroupedList>
          <GroupedListValueRow label={element.typ === "meilenstein" ? "Datum" : "Zeitraum"} wert={zeitraumText} />
          {element.typ !== "meilenstein" && (
            <GroupedListValueRow label="Fortschritt" wert={element.erledigt ? `${element.fortschritt} % · erledigt` : `${element.fortschritt} %`} />
          )}
          <GroupedListValueRow label="Zuständig" wert={element.zugewiesen_name ?? "Nicht zugewiesen"} last />
        </GroupedList>

        {fehler && (
          <div role="alert" className="rounded-[10px] bg-st-fehlt-bg px-3 py-2 text-sm text-st-fehlt">
            {fehler}
          </div>
        )}

        {element.typ === "schritt" && (
          <>
            <Abschnitt titel="Vorgang verknüpfen">
              <VorgangVerknuepfung projektId={projektId} element={element} busy={busy} onPatch={onPatch} onClose={onClose} />
            </Abschnitt>
            <Abschnitt titel="Fremdgewerk / Nachunternehmer">
              <PartnerAuswahl element={element} busy={busy} onPatch={onPatch} />
            </Abschnitt>
          </>
        )}
        {element.typ === "meilenstein" && (
          <Abschnitt titel="Materiallieferung verknüpfen">
            <BestellungVerknuepfung projektId={projektId} element={element} busy={busy} onPatch={onPatch} onClose={onClose} />
          </Abschnitt>
        )}
      </div>
    </Sheet>
  );
}
