// Ausfuellen-Seite fuer das Formular-Modul v2, gegen /api/form-submissions,
// mit CaptureRenderer/SummaryRenderer statt einem eigenen Feld-Loop: ein
// Schema, zwei Views (capture zum Ausfuellen, summary zum Nachlesen nach
// Abschluss) ohne doppelte Erfassungslogik -- siehe Abnahmekriterium "ein
// Schema bedient mindestens zwei Views ohne Duplizierung".
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { formModulApi, formSubmissionsApi } from "../../api/endpoints";
import { CaptureRenderer } from "../../components/formModul/CaptureRenderer";
import { SummaryRenderer } from "../../components/formModul/SummaryRenderer";
import { EmptyState } from "../../components/EmptyState";
import { openPdfBlob } from "../../utils/pdf";

export function FormSubmissionAusfuellenPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [fehler, setFehler] = useState<string | null>(null);
  const [gespeichert, setGespeichert] = useState(false);

  const { data: submission, isLoading: submissionLoading } = useQuery({
    queryKey: ["form-submission", id],
    queryFn: () => formSubmissionsApi.get(id!),
    enabled: !!id,
  });

  const { data: schema, isLoading: schemaLoading } = useQuery({
    queryKey: ["form-schema", submission?.schema_id],
    queryFn: () => formModulApi.getSchema(submission!.schema_id),
    enabled: !!submission,
  });

  const { data: views } = useQuery({
    queryKey: ["form-views", submission?.schema_id],
    queryFn: () => formModulApi.listViews(submission!.schema_id),
    enabled: !!submission,
  });

  const { data: rules } = useQuery({
    queryKey: ["form-rules", submission?.schema_id],
    queryFn: () => formModulApi.listRules(submission!.schema_id),
    enabled: !!submission,
  });

  const captureViewId = views?.find((v) => v.type === "capture")?.id;
  const summaryViewId = views?.find((v) => v.type === "summary")?.id;

  const { data: captureResolved } = useQuery({
    queryKey: ["form-view-resolved", captureViewId],
    queryFn: () => formModulApi.getView(submission!.schema_id, captureViewId!),
    enabled: !!submission && !!captureViewId,
  });

  const { data: summaryResolved } = useQuery({
    queryKey: ["form-view-resolved", summaryViewId],
    queryFn: () => formModulApi.getView(submission!.schema_id, summaryViewId!),
    enabled: !!submission && !!summaryViewId,
  });

  useEffect(() => {
    if (submission) setValues(submission.values);
  }, [submission]);

  const saveMutation = useMutation({
    mutationFn: () => formSubmissionsApi.updateValues(id!, values),
    onSuccess: () => {
      setFehler(null);
      setGespeichert(true);
      window.setTimeout(() => setGespeichert(false), 3000);
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Speichern fehlgeschlagen"),
  });

  const abschliessenMutation = useMutation({
    mutationFn: async () => {
      await formSubmissionsApi.updateValues(id!, values);
      return formSubmissionsApi.abschliessen(id!);
    },
    onSuccess: (result) => {
      setFehler(null);
      queryClient.invalidateQueries({ queryKey: ["form-submission", id] });
      queryClient.invalidateQueries({ queryKey: ["form-submissions", result.vorgang_id] });
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Formular konnte nicht abgeschlossen werden"),
  });

  const uploadMutation = useMutation({
    mutationFn: ({ fieldKey, file, filename }: { fieldKey: string; file: Blob; filename: string }) =>
      formSubmissionsApi.uploadDatei(id!, fieldKey, file, filename),
    onSuccess: (result) =>
      setValues((v) => {
        const datei = { key: result.key, url: result.url, content_type: result.content_type, filename: result.filename };
        const feldTyp = schema?.fields.find((f) => f.key === result.field_key)?.feld_typ;
        // foto_plan: Upload ersetzt nur das Hintergrundfoto, nicht den
        // ganzen (zusammengesetzten) Feld-Wert -- bereits gesetzte
        // Markierungen bleiben erhalten (siehe FormFieldRenderer.tsx).
        if (feldTyp === "foto_plan") {
          const bisher = v[result.field_key] as { markierungen?: unknown[] } | undefined;
          return { ...v, [result.field_key]: { foto: datei, markierungen: bisher?.markierungen ?? [] } };
        }
        return { ...v, [result.field_key]: datei };
      }),
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Upload fehlgeschlagen"),
  });

  const pdfMutation = useMutation({
    mutationFn: async () => {
      if (submission?.status !== "abgeschlossen") await formSubmissionsApi.updateValues(id!, values);
      return formSubmissionsApi.pdf(id!);
    },
    onSuccess: openPdfBlob,
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "PDF konnte nicht erzeugt werden"),
  });

  if (submissionLoading || schemaLoading) return <p className="text-center text-sm text-label2">Lädt…</p>;
  if (!submission || !schema) return <EmptyState icon={FileText} text="Formular nicht gefunden." />;

  const readOnly = submission.status === "abgeschlossen";

  return (
    <div className="space-y-3 pb-24">
      <button onClick={() => navigate(-1)} className="text-sm text-label2">
        ← Zurück
      </button>

      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-label">{schema.name}</h1>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
            readOnly ? "bg-st-erledigt-bg text-st-erledigt  " : "bg-st-arbeit-bg text-st-arbeit  "
          }`}
        >
          {readOnly ? "Abgeschlossen" : "Offen"}
        </span>
      </div>

      {readOnly && summaryViewId ? (
        <SummaryRenderer
          fields={schema.fields}
          groups={schema.groups}
          rules={rules ?? []}
          elements={summaryResolved?.elements ?? []}
          values={submission.values}
          viewId={summaryViewId}
        />
      ) : (
        <CaptureRenderer
          fields={schema.fields}
          groups={schema.groups}
          rules={rules ?? []}
          elements={captureResolved?.elements ?? []}
          values={values}
          onChange={setValues}
          readOnly={readOnly}
          viewId={captureViewId ?? null}
          onUpload={(fieldKey, file, filename) => uploadMutation.mutate({ fieldKey, file, filename })}
          hochladenPending={uploadMutation.isPending}
        />
      )}

      {fehler ? (
        <p className="text-sm text-st-fehlt ">{fehler}</p>
      ) : (
        gespeichert && <p className="text-sm text-st-erledigt ">Gespeichert.</p>
      )}

      <button
        onClick={() => pdfMutation.mutate()}
        disabled={pdfMutation.isPending}
        className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md bg-slate-100 py-2 text-sm font-medium text-label disabled:opacity-50 dark:bg-stone-800 "
      >
        <FileText size={16} /> {readOnly ? "Als PDF öffnen" : "PDF-Vorschau ansehen"}
      </button>

      {!readOnly && (
        <div className="fixed inset-x-0 bottom-16 z-10 flex gap-2 px-4">
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-white py-2 text-sm font-medium text-label shadow-md disabled:opacity-50 dark:bg-stone-800 "
          >
            Speichern
          </button>
          <button
            onClick={() => {
              if (window.confirm("Formular abschließen? Danach nicht mehr bearbeitbar.")) {
                abschliessenMutation.mutate();
              }
            }}
            disabled={abschliessenMutation.isPending}
            className="btn-touch flex-1 rounded-md btn-ap-primary py-2 text-sm font-medium shadow-md disabled:opacity-50"
          >
            Abschließen
          </button>
        </div>
      )}
    </div>
  );
}
