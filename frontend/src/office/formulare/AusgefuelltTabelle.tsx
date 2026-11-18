import { ChevronLeft, ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";

import { StatusPille } from "../../components/apple/StatusPille";
import { ClaudeMarke } from "../../components/formModul/ClaudeMarke";
import type { FormSubmissionUebersicht } from "../../types";
import { TabellenRahmen } from "../OfficeUi";
import { relativDatum } from "./formulareUtil";

export const SEITENGROESSE = 100;

/** Solange ein von Claude vorbefülltes Protokoll offen ist, steht dort "Entwurf von
 * Claude"; nach dem Abschluss der Mensch, der es abgeschlossen hat (ausgefuellt_von_name). */
export function AusgefuelltVon({ e }: { e: FormSubmissionUebersicht }) {
  if (e.erstellt_via === "ki" && e.status === "offen") return <ClaudeMarke label="Entwurf von Claude" klein />;
  return <>{e.ausgefuellt_von_name ?? "—"}</>;
}

export function AusgefuelltTabelle({
  eintraege,
  auswahlId,
  onWaehle,
  hervorgehoben = [],
  ohneVorlage = false,
}: {
  eintraege: FormSubmissionUebersicht[];
  auswahlId: string | null;
  onWaehle: (e: FormSubmissionUebersicht) => void;
  /** Spalten-Ids mit aktivem Filter (Kopf in Tint). */
  hervorgehoben?: string[];
  /** Im Baukasten ist die Vorlage durch den Filter bekannt. */
  ohneVorlage?: boolean;
}) {
  const kopf = (id: string, label: string) => (
    <th scope="col" className={`px-3 py-2 font-medium tracking-wide uppercase ${hervorgehoben.includes(id) ? "text-tint-text" : ""}`}>
      {label}
    </th>
  );
  return (
    <TabellenRahmen>
      <table className="w-full text-left text-fliess">
        <caption className="sr-only">Ausgefüllte Protokolle, neueste zuerst</caption>
        <thead className="text-meta text-label2">
          <tr className="border-b border-sepstrong">
            {!ohneVorlage && kopf("vorlage", "Vorlage")}
            {kopf("vorgang", "Vorgang")}
            {kopf("kunde", "Kunde")}
            {kopf("status", "Status")}
            {kopf("techniker", "Ausgefüllt von")}
            {kopf("datum", "Datum")}
          </tr>
        </thead>
        <tbody>
          {eintraege.map((e) => {
            const gewaehlt = e.id === auswahlId;
            return (
              <tr
                key={e.id}
                tabIndex={0}
                aria-selected={gewaehlt}
                onClick={() => onWaehle(e)}
                onKeyDown={(ev) => {
                  if (ev.key === "Enter" && ev.target === ev.currentTarget) onWaehle(e);
                }}
                className={`cursor-pointer border-b border-sep last:border-b-0 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-tint ${
                  gewaehlt ? "bg-tintbg" : "hover:bg-fill"
                }`}
              >
                {!ohneVorlage && <td className="max-w-[220px] px-3 py-2 font-semibold text-label">{e.schema_name}</td>}
                <td className="max-w-[260px] px-3 py-2 text-label">
                  <span className="flex min-w-0 gap-1.5">
                    <span className="shrink-0 text-label2">{e.vorgangsnummer}</span>
                    <span className="truncate">{e.vorgang_titel}</span>
                  </span>
                </td>
                <td className="px-3 py-2 text-label">{e.kunde_name ?? "—"}</td>
                <td className="px-3 py-2">
                  {e.status === "offen" ? <StatusPille status="arbeit" label="Offen" /> : <StatusPille status="erledigt" label="Abgeschlossen" />}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-label">
                  <AusgefuelltVon e={e} />
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-label2">{relativDatum(e.abgeschlossen_am ?? e.created_at, true)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </TabellenRahmen>
  );
}

export function Seitenwahl({ seite, gesamt, anzahl, onSeite }: { seite: number; gesamt: number; anzahl: number; onSeite: (s: number) => void }) {
  if (gesamt <= SEITENGROESSE) return null;
  const von = (seite - 1) * SEITENGROESSE + 1;
  return (
    <nav aria-label="Seiten" className="mt-3 flex items-center justify-between text-sekundaer text-label2">
      <span>
        {von}–{von + anzahl - 1} von {gesamt.toLocaleString("de-DE")}
      </span>
      <div className="flex gap-2">
        <button type="button" className="btn-ap inline-flex h-8 items-center gap-1 px-3 text-sekundaer" disabled={seite <= 1} onClick={() => onSeite(seite - 1)}>
          <ChevronLeft size={14} aria-hidden="true" /> Neuere
        </button>
        <button
          type="button"
          className="btn-ap inline-flex h-8 items-center gap-1 px-3 text-sekundaer"
          disabled={seite * SEITENGROESSE >= gesamt}
          onClick={() => onSeite(seite + 1)}
        >
          Ältere <ChevronRight size={14} aria-hidden="true" />
        </button>
      </div>
    </nav>
  );
}

// Link nur für die Panel-Aktion; hier exportiert, damit die Tabelle keinen eigenen Navigationspfad kennen muss.
export function VorgangLink({ id, className, children }: { id: string; className?: string; children: React.ReactNode }) {
  return (
    <Link to={`/vorgaenge/${id}`} className={className}>
      {children}
    </Link>
  );
}
