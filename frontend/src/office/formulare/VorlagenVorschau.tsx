import { FileText } from "lucide-react";
import { useMemo, useState } from "react";

import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { CaptureRenderer } from "../../components/formModul/CaptureRenderer";
import { SummaryRenderer } from "../../components/formModul/SummaryRenderer";
import { DetailSkeleton } from "../../components/Skeleton";
import { beispielWerte } from "./beispielwerte";
import { PdfVorschau } from "./PdfVorschau";
import { useSchemaDaten } from "./useSchemaDaten";

export type VorschauAnsicht = "erfassung" | "zusammenfassung" | "druck";

const KEIN_WERT: Record<string, unknown> = {};
const nichts = () => {};

/** Lesende Vorschau einer Vorlage mit Umschalter Erfassung | Zusammenfassung | Druck.
 * Erfassung zeigt das leere Formular wie der Techniker es sieht (CaptureRenderer,
 * nur lesend), Zusammenfassung Beispielwerte, Druck das Server-PDF. */
export function VorlagenVorschau({ schemaId }: { schemaId: string }) {
  const [ansicht, setAnsicht] = useState<VorschauAnsicht>("erfassung");
  const { schema, rules, captureId, summaryId, printId, capture, summary } = useSchemaDaten(schemaId);
  const s = schema.data;
  const beispiel = useMemo(() => (s ? beispielWerte(s.fields, s.groups) : KEIN_WERT), [s]);

  if (schema.error && !s) return <FehlerZustand fehler={schema.error} was="Die Vorlage" onErneut={() => void schema.refetch()} />;
  if (!s) return <DetailSkeleton />;

  return (
    <div className="space-y-3">
      <SegmentedControl<VorschauAnsicht>
        ariaLabel="Vorschau-Ansicht"
        wert={ansicht}
        onChange={setAnsicht}
        optionen={[
          { wert: "erfassung", label: "Erfassung" },
          { wert: "zusammenfassung", label: "Zusammenfassung" },
          { wert: "druck", label: "Druck" },
        ]}
      />
      {s.fields.length === 0 && ansicht !== "druck" ? (
        <EmptyState icon={FileText} text="Diese Vorlage hat noch keine Felder. Im Baukasten lassen sie sich anlegen." />
      ) : ansicht === "erfassung" ? (
        <CaptureRenderer
          fields={s.fields}
          groups={s.groups}
          rules={rules.data ?? []}
          elements={capture.data?.elements ?? []}
          values={KEIN_WERT}
          onChange={nichts}
          readOnly
          viewId={captureId ?? null}
        />
      ) : ansicht === "zusammenfassung" ? (
        <SummaryRenderer
          fields={s.fields}
          groups={s.groups}
          rules={rules.data ?? []}
          elements={summary.data?.elements ?? []}
          values={beispiel}
          viewId={summaryId ?? null}
        />
      ) : (
        <PdfVorschau schemaId={schemaId} viewId={printId} />
      )}
    </div>
  );
}
