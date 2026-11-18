import { useQuery } from "@tanstack/react-query";

import { formModulApi } from "../../api/endpoints";

/** Schema samt Regeln, Ansichten und den aufgelösten Elementen von Erfassung und
 * Zusammenfassung -- dieselben Query-Keys wie der Baukasten, damit der Cache
 * zwischen Vorschau-Panel und Editor geteilt wird. */
export function useSchemaDaten(schemaId: string | undefined) {
  const aktiv = !!schemaId;
  const schema = useQuery({ queryKey: ["form-schema", schemaId], queryFn: () => formModulApi.getSchema(schemaId!), enabled: aktiv });
  const views = useQuery({ queryKey: ["form-views", schemaId], queryFn: () => formModulApi.listViews(schemaId!), enabled: aktiv });
  const rules = useQuery({ queryKey: ["form-rules", schemaId], queryFn: () => formModulApi.listRules(schemaId!), enabled: aktiv });
  const captureId = views.data?.find((v) => v.type === "capture")?.id;
  const summaryId = views.data?.find((v) => v.type === "summary")?.id;
  const printId = views.data?.find((v) => v.type === "print")?.id;
  const capture = useQuery({
    queryKey: ["form-view-resolved", captureId],
    queryFn: () => formModulApi.getView(schemaId!, captureId!),
    enabled: aktiv && !!captureId,
  });
  const summary = useQuery({
    queryKey: ["form-view-resolved", summaryId],
    queryFn: () => formModulApi.getView(schemaId!, summaryId!),
    enabled: aktiv && !!summaryId,
  });
  return { schema, views, rules, captureId, summaryId, printId, capture, summary };
}
