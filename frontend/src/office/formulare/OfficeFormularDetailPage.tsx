import { useQuery } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import { formulareApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FormularRasterEditor } from "../../pages/feld/FormularRasterEditor";
import { SeitenKopf } from "../OfficeUi";

/** Formular-Editor am Schreibtisch. Nutzt denselben Raster-Editor wie die
 * Feld-App -- nur ohne dessen CSS-Ausbruch aus dem engen Mobil-Rahmen, den es
 * hier nicht gibt (siehe Kommentar in FormularRasterEditor). */
export function OfficeFormularDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: formular, isLoading } = useQuery({
    queryKey: ["formular", id],
    queryFn: () => formulareApi.get(id!),
    enabled: !!id,
  });

  if (isLoading) {
    return <p className="py-10 text-center text-sm text-slate-400 dark:text-stone-500">Lädt…</p>;
  }
  if (!formular) {
    return <EmptyState icon={Pencil} text="Formular nicht gefunden." />;
  }

  return (
    <div>
      <SeitenKopf titel={formular.name}>
        <button
          onClick={() => navigate("/formulare")}
          className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-500 hover:text-slate-700 dark:border-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
        >
          ← Alle Formulare
        </button>
      </SeitenKopf>
      <FormularRasterEditor formular={formular} vollbreiteAusbruch={false} />
    </div>
  );
}
