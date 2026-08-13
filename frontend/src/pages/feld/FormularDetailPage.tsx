import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useParams, useNavigate } from "react-router-dom";

import { formulareApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import type { Formular, Leistungstyp } from "../../types";
import { LEISTUNGSTYP_LABEL } from "../../utils/formular";
import { FormularRasterEditor } from "./FormularRasterEditor";

const LEISTUNGSTYPEN: Leistungstyp[] = [
  "installation",
  "pruefung",
  "wartung",
  "stoerung",
  "beratung",
  "planung",
];

function AuftragstypZuordnungen({ formular }: { formular: Formular }) {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["formular", formular.id] });

  const createMutation = useMutation({
    mutationFn: (leistungstyp: Leistungstyp) => formulareApi.createZuordnung(formular.id, { leistungstyp }),
    onSuccess: invalidate,
  });
  const updateMutation = useMutation({
    mutationFn: ({ zuordnungId, pflicht }: { zuordnungId: string; pflicht: boolean }) =>
      formulareApi.updateZuordnung(formular.id, zuordnungId, pflicht),
    onSuccess: invalidate,
  });
  const deleteMutation = useMutation({
    mutationFn: (zuordnungId: string) => formulareApi.deleteZuordnung(formular.id, zuordnungId),
    onSuccess: invalidate,
  });

  return (
    <div>
      <h2 className="mb-1 px-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
        Auftragstypen
      </h2>
      <p className="mb-2 px-1 text-xs text-slate-400 dark:text-stone-500">
        Bei welchen Auftragstypen wird dieses Formular Technikern zum Ausfüllen angeboten?
      </p>
      <div className="divide-y divide-slate-100 rounded-lg bg-white shadow-xs dark:divide-stone-800 dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        {LEISTUNGSTYPEN.map((typ) => {
          const zuordnung = formular.zuordnungen.find((z) => z.leistungstyp === typ);
          const zugeordnet = !!zuordnung;
          return (
            <div key={typ} className="flex items-center gap-3 p-3">
              <label className="flex flex-1 items-center gap-2 text-sm text-slate-700 dark:text-stone-200">
                <input
                  type="checkbox"
                  checked={zugeordnet}
                  onChange={(e) => {
                    if (e.target.checked) createMutation.mutate(typ);
                    else if (zuordnung) deleteMutation.mutate(zuordnung.id);
                  }}
                  className="h-4 w-4 rounded-xs border-slate-300 dark:border-stone-600"
                />
                {LEISTUNGSTYP_LABEL[typ]}
              </label>
              <label
                className={`flex items-center gap-1.5 text-xs ${
                  zugeordnet ? "text-slate-500 dark:text-stone-400" : "text-slate-300 dark:text-stone-600"
                }`}
              >
                <input
                  type="checkbox"
                  disabled={!zugeordnet}
                  checked={zuordnung?.pflicht_vor_abschluss ?? false}
                  onChange={(e) =>
                    zuordnung && updateMutation.mutate({ zuordnungId: zuordnung.id, pflicht: e.target.checked })
                  }
                  className="h-3.5 w-3.5 rounded-xs border-slate-300 disabled:opacity-40 dark:border-stone-600"
                />
                Pflicht vor Abschluss
              </label>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function FormularDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: formular, isLoading } = useQuery({
    queryKey: ["formular", id],
    queryFn: () => formulareApi.get(id!),
    enabled: !!id,
  });

  const updateFormularMutation = useMutation({
    mutationFn: (body: Partial<{ name: string; beschreibung: string; aktiv: boolean }>) =>
      formulareApi.update(id!, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["formular", id] }),
  });

  if (isLoading) {
    return <p className="text-center text-sm text-slate-500 dark:text-stone-400">Lädt…</p>;
  }
  if (!formular) {
    return <EmptyState icon={Pencil} text="Formular nicht gefunden." />;
  }

  return (
    <div className="space-y-4">
      <button onClick={() => navigate("/formulare")} className="text-sm text-slate-500 dark:text-stone-400">
        ← Alle Formulare
      </button>

      <div className="rounded-lg bg-white p-4 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <input
          value={formular.name}
          onChange={(e) => updateFormularMutation.mutate({ name: e.target.value })}
          className="w-full border-none bg-transparent p-0 text-lg font-bold text-slate-800 focus:outline-hidden dark:text-stone-100"
        />
        <input
          value={formular.beschreibung ?? ""}
          onChange={(e) => updateFormularMutation.mutate({ beschreibung: e.target.value })}
          placeholder="Beschreibung hinzufügen…"
          className="mt-1 w-full border-none bg-transparent p-0 text-sm text-slate-500 focus:outline-hidden dark:text-stone-400"
        />
        <label className="mt-3 flex items-center gap-2 text-sm text-slate-600 dark:text-stone-300">
          <input
            type="checkbox"
            checked={formular.aktiv}
            onChange={(e) => updateFormularMutation.mutate({ aktiv: e.target.checked })}
            className="h-4 w-4 rounded-xs border-slate-300 dark:border-stone-600"
          />
          Aktiv (für Techniker sichtbar)
        </label>
      </div>

      <AuftragstypZuordnungen formular={formular} />

      <FormularRasterEditor formular={formular} />
    </div>
  );
}
