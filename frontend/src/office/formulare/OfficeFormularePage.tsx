import { useQuery } from "@tanstack/react-query";
import { FileText, Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { formulareApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { IconBadge } from "../../components/IconBadge";
import { LEISTUNGSTYP_LABEL } from "../../config/vorgangDarstellung";
import { Karte, SeitenKopf } from "../OfficeUi";

/** Uebersicht aller Formular-Vorlagen als Raster. Am Schreibtisch will man
 * sehen, welche Vorlagen es gibt und wo sie greifen -- die Handy-App zeigt
 * dafuer eine reine Liste, was bei vielen Vorlagen unuebersichtlich wird. */
export function OfficeFormularePage() {
  const navigate = useNavigate();
  const { data: formulare, isLoading } = useQuery({
    queryKey: ["formulare"],
    queryFn: () => formulareApi.list(),
  });

  return (
    <div>
      <SeitenKopf titel="Formulare" anzahl={formulare?.length}>
        <button
          onClick={() => navigate("/formulare")}
          className="btn-clay flex items-center gap-1.5 rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-2 text-xs font-semibold text-white"
        >
          <Plus size={14} strokeWidth={2.5} />
          Neues Formular
        </button>
      </SeitenKopf>

      {isLoading ? (
        <p className="py-10 text-center text-sm text-slate-400 dark:text-stone-500">Lädt…</p>
      ) : !formulare || formulare.length === 0 ? (
        <EmptyState icon={FileText} text="Noch keine Formulare angelegt." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {formulare.map((f) => (
            <button
              key={f.id}
              onClick={() => navigate(`/formulare/${f.id}`)}
              className="text-left"
            >
              <Karte className="card-interactive h-full p-4">
                <div className="mb-2.5 flex items-center gap-2.5">
                  <IconBadge icon={FileText} tone={f.aktiv ? "violet" : "slate"} size="sm" />
                  <p className="text-[13px] font-semibold text-slate-800 dark:text-stone-100">
                    {f.name}
                  </p>
                </div>
                <p className="mb-2.5 text-[11px] text-slate-500 dark:text-stone-400">
                  {f.felder.length} {f.felder.length === 1 ? "Feld" : "Felder"} ·{" "}
                  {f.anzahl_seiten} {f.anzahl_seiten === 1 ? "Seite" : "Seiten"}
                  {!f.aktiv && " · inaktiv"}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {f.zuordnungen.map((z) => (
                    <span
                      key={z.id}
                      className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-400"
                    >
                      {LEISTUNGSTYP_LABEL[z.leistungstyp] ?? z.leistungstyp}
                      {z.pflicht_vor_abschluss && " · Pflicht"}
                    </span>
                  ))}
                </div>
              </Karte>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
