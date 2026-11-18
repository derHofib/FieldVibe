import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, ExternalLink } from "lucide-react";
import { useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { formSubmissionsApi } from "../../api/endpoints";
import { StatusPille } from "../../components/apple/StatusPille";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SummaryRenderer } from "../../components/formModul/SummaryRenderer";
import { DetailSkeleton } from "../../components/Skeleton";
import type { FormSubmissionUebersicht } from "../../types";
import { downloadBlob } from "../../utils/download";
import { AusgefuelltVon, VorgangLink } from "./AusgefuelltTabelle";
import { langesDatum, relativDatum } from "./formulareUtil";
import { useSchemaDaten } from "./useSchemaDaten";

/** Lesbare Zusammenfassung eines ausgefüllten Protokolls: Werte kommen aus der
 * Submission, Felder/Regeln aus der Vorlage (SummaryRenderer, dieselbe Darstellung
 * wie am Vorgang). PDF über den bestehenden Submission-Endpunkt. */
export function AusgefuelltPanel({ eintrag }: { eintrag: FormSubmissionUebersicht }) {
  const [pdfFehler, setPdfFehler] = useState<string | null>(null);
  const sub = useQuery({ queryKey: ["form-submission", eintrag.id], queryFn: () => formSubmissionsApi.get(eintrag.id) });
  const { schema, rules, summaryId, summary } = useSchemaDaten(eintrag.schema_id);
  const s = schema.data;
  const werte = useMemo(() => sub.data?.values ?? {}, [sub.data]);

  const pdf = useMutation({
    mutationFn: () => formSubmissionsApi.pdf(eintrag.id),
    onSuccess: (blob) => {
      setPdfFehler(null);
      downloadBlob(blob, `${eintrag.schema_name} ${eintrag.vorgangsnummer}.pdf`);
    },
    onError: (err) => setPdfFehler(err instanceof ApiError ? err.message : "Das PDF konnte nicht erzeugt werden."),
  });

  const zeitpunkt = eintrag.abgeschlossen_am ?? eintrag.created_at;

  return (
    <div className="space-y-3 pt-3">
      <div className="flex items-start justify-between gap-2">
        <h2 className="min-w-0 text-zeile font-semibold text-label">
          {eintrag.schema_name} <span className="font-normal text-label2">· {eintrag.vorgangsnummer}</span>
        </h2>
        <div className="flex shrink-0 items-center gap-2">
          <VorgangLink id={eintrag.vorgang_id} className="btn-ap inline-flex h-8 items-center gap-1.5 px-3 text-sekundaer">
            <ExternalLink size={14} aria-hidden="true" /> Zum Vorgang
          </VorgangLink>
          <button
            type="button"
            onClick={() => pdf.mutate()}
            disabled={pdf.isPending}
            className="btn-ap-primary inline-flex h-8 items-center gap-1.5 px-3 text-sekundaer font-semibold disabled:opacity-50"
          >
            <Download size={14} aria-hidden="true" /> {pdf.isPending ? "Erzeuge …" : "PDF"}
          </button>
        </div>
      </div>
      {pdfFehler && (
        <p role="alert" className="text-sekundaer text-st-fehlt">
          {pdfFehler}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sekundaer text-label2">
        {eintrag.status === "offen" ? <StatusPille status="arbeit" label="Offen" /> : <StatusPille status="erledigt" label="Abgeschlossen" />}
        <span title={langesDatum(zeitpunkt)}>{relativDatum(zeitpunkt, true)}</span>
        <span>·</span>
        <span className="text-label">
          <AusgefuelltVon e={eintrag} />
        </span>
        <span>· Version {eintrag.schema_version}</span>
      </div>
      <div>
        <p className="text-fliess font-semibold text-label">{eintrag.vorgang_titel}</p>
        {eintrag.kunde_name && <p className="text-sekundaer text-label2">{eintrag.kunde_name}</p>}
      </div>

      {sub.error && !sub.data ? (
        <FehlerZustand fehler={sub.error} was="Das Protokoll" onErneut={() => void sub.refetch()} />
      ) : !sub.data || !s ? (
        <DetailSkeleton />
      ) : (
        <SummaryRenderer
          fields={s.fields}
          groups={s.groups}
          rules={rules.data ?? []}
          elements={summary.data?.elements ?? []}
          values={werte}
          viewId={summaryId ?? null}
        />
      )}
    </div>
  );
}
