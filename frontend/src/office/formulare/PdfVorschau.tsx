import { useQuery } from "@tanstack/react-query";
import { FileX } from "lucide-react";
import { useEffect, useState } from "react";

import { formModulApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { Skeleton } from "../../components/Skeleton";

/** Echtes PDF der Druckansicht (Server-Rendering, nicht nachgebaut), als Blob-URL
 * eingebettet. Ohne submissionId rendert der Server Beispieldaten. */
export function PdfVorschau({
  schemaId,
  viewId,
  submissionId,
  hoehe = "h-[640px]",
}: {
  schemaId: string;
  viewId: string | null | undefined;
  submissionId?: string;
  hoehe?: string;
}) {
  const { data: blob, isLoading, error, refetch } = useQuery({
    queryKey: ["form-vorschau-pdf", schemaId, viewId, submissionId ?? null],
    queryFn: () => formModulApi.vorschauPdf(schemaId, viewId!, submissionId),
    enabled: !!viewId,
    staleTime: 30_000,
  });
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!blob) {
      setUrl(null);
      return;
    }
    const neu = URL.createObjectURL(blob);
    setUrl(neu);
    return () => URL.revokeObjectURL(neu);
  }, [blob]);

  if (!viewId) {
    return <EmptyState icon={FileX} text="Für diese Vorlage gibt es noch keine Druckansicht." />;
  }
  if (isLoading) return <Skeleton className={`${hoehe} w-full`} />;
  if (error) return <FehlerZustand fehler={error} was="Die PDF-Vorschau" onErneut={() => void refetch()} />;
  if (!url) return null;
  return <iframe src={url} title="PDF-Vorschau der Druckansicht" className={`${hoehe} w-full rounded-[var(--radius-ap-md)] bg-fill`} />;
}
