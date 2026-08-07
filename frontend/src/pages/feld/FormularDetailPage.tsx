import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, Pencil, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { formulareApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { IconBadge } from "../../components/IconBadge";
import type { Formular, Formularfeld, FormularfeldTyp, Leistungstyp } from "../../types";
import { FORMULARFELD_TYP_ICON, FORMULARFELD_TYP_LABEL, LEISTUNGSTYP_LABEL } from "../../utils/formular";

const FELD_TYP_OPTIONEN = Object.entries(FORMULARFELD_TYP_LABEL) as [FormularfeldTyp, string][];
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
      <div className="divide-y divide-slate-100 rounded-lg bg-white shadow-sm dark:divide-stone-800 dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
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
                  className="h-4 w-4 rounded border-slate-300 dark:border-stone-600"
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
                  className="h-3.5 w-3.5 rounded border-slate-300 disabled:opacity-40 dark:border-stone-600"
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

interface FeldFormValues {
  feld_typ: FormularfeldTyp;
  label: string;
  hilfetext: string;
  pflichtfeld: boolean;
  werte: string;
  min: string;
  max: string;
}

function leereWerte(feld?: Formularfeld): FeldFormValues {
  const optionen = feld?.optionen ?? {};
  return {
    feld_typ: feld?.feld_typ ?? "text",
    label: feld?.label ?? "",
    hilfetext: feld?.hilfetext ?? "",
    pflichtfeld: feld?.pflichtfeld ?? false,
    werte: Array.isArray(optionen.werte) ? (optionen.werte as string[]).join("\n") : "",
    min: optionen.min !== undefined ? String(optionen.min) : "1",
    max: optionen.max !== undefined ? String(optionen.max) : "5",
  };
}

function baueOptionen(values: FeldFormValues): Record<string, unknown> {
  if (values.feld_typ === "dropdown" || values.feld_typ === "mehrfachauswahl") {
    return {
      werte: values.werte
        .split("\n")
        .map((w) => w.trim())
        .filter(Boolean),
    };
  }
  if (values.feld_typ === "bewertung") {
    return { min: Number(values.min) || 1, max: Number(values.max) || 5 };
  }
  return {};
}

function FeldForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
  isPending,
}: {
  initial?: Formularfeld;
  submitLabel: string;
  onSubmit: (values: FeldFormValues) => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [values, setValues] = useState<FeldFormValues>(leereWerte(initial));

  function set<K extends keyof FeldFormValues>(key: K, value: FeldFormValues[K]) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!values.label.trim()) return;
    onSubmit(values);
  }

  return (
    <form
      onSubmit={submit}
      className="space-y-3 rounded-lg bg-cyan-50/60 p-3 dark:bg-cyan-500/5 dark:ring-1 dark:ring-cyan-500/20"
    >
      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-stone-400">Feldtyp</label>
        <select
          value={values.feld_typ}
          onChange={(e) => set("feld_typ", e.target.value as FormularfeldTyp)}
          className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        >
          {FELD_TYP_OPTIONEN.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-stone-400">
          {values.feld_typ === "abschnitt" ? "Überschrift" : "Frage / Label"}
        </label>
        <input
          value={values.label}
          onChange={(e) => set("label", e.target.value)}
          autoFocus
          placeholder={values.feld_typ === "abschnitt" ? "z.B. Sicherheitscheck" : "z.B. Anlagenbezeichnung"}
          className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        />
      </div>

      {values.feld_typ !== "abschnitt" && (
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-stone-400">
            Hilfetext (optional)
          </label>
          <input
            value={values.hilfetext}
            onChange={(e) => set("hilfetext", e.target.value)}
            placeholder="Erklärung, die der Techniker beim Ausfüllen sieht"
            className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        </div>
      )}

      {(values.feld_typ === "dropdown" || values.feld_typ === "mehrfachauswahl") && (
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-stone-400">
            Auswahlmöglichkeiten (eine je Zeile)
          </label>
          <textarea
            value={values.werte}
            onChange={(e) => set("werte", e.target.value)}
            rows={3}
            placeholder={"z.B.\nIn Ordnung\nMangel festgestellt\nNicht prüfbar"}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        </div>
      )}

      {values.feld_typ === "bewertung" && (
        <div className="flex gap-2">
          <div className="flex-1">
            <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-stone-400">Skala von</label>
            <input
              type="number"
              value={values.min}
              onChange={(e) => set("min", e.target.value)}
              className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-stone-400">bis</label>
            <input
              type="number"
              value={values.max}
              onChange={(e) => set("max", e.target.value)}
              className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
          </div>
        </div>
      )}

      {values.feld_typ !== "abschnitt" && (
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-stone-300">
          <input
            type="checkbox"
            checked={values.pflichtfeld}
            onChange={(e) => set("pflichtfeld", e.target.checked)}
            className="h-4 w-4 rounded border-slate-300 dark:border-stone-600"
          />
          Pflichtfeld
        </label>
      )}

      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600 dark:bg-stone-800 dark:text-stone-300"
        >
          Abbrechen
        </button>
        <button
          type="submit"
          disabled={isPending}
          className="btn-touch btn-clay rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {submitLabel}
        </button>
      </div>
    </form>
  );
}

export function FormularDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [neuesFeldOffen, setNeuesFeldOffen] = useState(false);
  const [bearbeitenId, setBearbeitenId] = useState<string | null>(null);

  const { data: formular, isLoading } = useQuery({
    queryKey: ["formular", id],
    queryFn: () => formulareApi.get(id!),
    enabled: !!id,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["formular", id] });

  const updateFormularMutation = useMutation({
    mutationFn: (body: Partial<{ name: string; beschreibung: string; aktiv: boolean }>) =>
      formulareApi.update(id!, body),
    onSuccess: invalidate,
  });

  const createFeldMutation = useMutation({
    mutationFn: (values: FeldFormValues) =>
      formulareApi.createFeld(id!, {
        feld_typ: values.feld_typ,
        label: values.label.trim(),
        hilfetext: values.hilfetext.trim() || undefined,
        pflichtfeld: values.pflichtfeld,
        reihenfolge: formular?.felder.length ?? 0,
        optionen: baueOptionen(values),
      }),
    onSuccess: () => {
      invalidate();
      setNeuesFeldOffen(false);
    },
  });

  const updateFeldMutation = useMutation({
    mutationFn: ({ feldId, values }: { feldId: string; values: FeldFormValues }) =>
      formulareApi.updateFeld(id!, feldId, {
        feld_typ: values.feld_typ,
        label: values.label.trim(),
        hilfetext: values.hilfetext.trim() || null,
        pflichtfeld: values.pflichtfeld,
        optionen: baueOptionen(values),
      }),
    onSuccess: () => {
      invalidate();
      setBearbeitenId(null);
    },
  });

  const deleteFeldMutation = useMutation({
    mutationFn: (feldId: string) => formulareApi.deleteFeld(id!, feldId),
    onSuccess: invalidate,
  });

  const reihenfolgeMutation = useMutation({
    mutationFn: (feldIds: string[]) => formulareApi.reihenfolgeFelder(id!, feldIds),
    onSuccess: invalidate,
  });

  function verschieben(feldId: string, richtung: -1 | 1) {
    if (!formular) return;
    const sortiert = [...formular.felder].sort((a, b) => a.reihenfolge - b.reihenfolge);
    const index = sortiert.findIndex((f) => f.id === feldId);
    const zielIndex = index + richtung;
    if (zielIndex < 0 || zielIndex >= sortiert.length) return;
    [sortiert[index], sortiert[zielIndex]] = [sortiert[zielIndex], sortiert[index]];
    reihenfolgeMutation.mutate(sortiert.map((f) => f.id));
  }

  if (isLoading) {
    return <p className="text-center text-sm text-slate-500 dark:text-stone-400">Lädt…</p>;
  }
  if (!formular) {
    return <EmptyState icon={Pencil} text="Formular nicht gefunden." />;
  }

  const felder = [...formular.felder].sort((a, b) => a.reihenfolge - b.reihenfolge);
  const fehlerText = (err: unknown) =>
    err instanceof ApiError ? err.message : "Änderung konnte nicht gespeichert werden";

  return (
    <div className="space-y-4">
      <button onClick={() => navigate("/formulare")} className="text-sm text-slate-500 dark:text-stone-400">
        ← Alle Formulare
      </button>

      <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <input
          value={formular.name}
          onChange={(e) => updateFormularMutation.mutate({ name: e.target.value })}
          className="w-full border-none bg-transparent p-0 text-lg font-bold text-slate-800 focus:outline-none dark:text-stone-100"
        />
        <input
          value={formular.beschreibung ?? ""}
          onChange={(e) => updateFormularMutation.mutate({ beschreibung: e.target.value })}
          placeholder="Beschreibung hinzufügen…"
          className="mt-1 w-full border-none bg-transparent p-0 text-sm text-slate-500 focus:outline-none dark:text-stone-400"
        />
        <label className="mt-3 flex items-center gap-2 text-sm text-slate-600 dark:text-stone-300">
          <input
            type="checkbox"
            checked={formular.aktiv}
            onChange={(e) => updateFormularMutation.mutate({ aktiv: e.target.checked })}
            className="h-4 w-4 rounded border-slate-300 dark:border-stone-600"
          />
          Aktiv (für Techniker sichtbar)
        </label>
      </div>

      <AuftragstypZuordnungen formular={formular} />

      <div>
        <h2 className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
          Felder
        </h2>

        {felder.length === 0 && !neuesFeldOffen && (
          <EmptyState icon={Plus} text="Noch keine Felder -- füge das erste Feld hinzu." />
        )}

        <div className="space-y-1.5">
          {felder.map((feld, index) =>
            bearbeitenId === feld.id ? (
              <FeldForm
                key={feld.id}
                initial={feld}
                submitLabel="Speichern"
                isPending={updateFeldMutation.isPending}
                onCancel={() => setBearbeitenId(null)}
                onSubmit={(values) => updateFeldMutation.mutate({ feldId: feld.id, values })}
              />
            ) : (
              <div
                key={feld.id}
                className="flex items-center gap-2 rounded-lg bg-white p-3 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
              >
                <IconBadge icon={FORMULARFELD_TYP_ICON[feld.feld_typ]} tone="cyan" size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-slate-800 dark:text-stone-100">
                    {feld.label}
                    {feld.pflichtfeld && <span className="ml-1.5 text-rose-500">*</span>}
                  </div>
                  <div className="text-xs text-slate-400 dark:text-stone-500">
                    {FORMULARFELD_TYP_LABEL[feld.feld_typ]}
                  </div>
                </div>
                <div className="flex items-center gap-0.5">
                  <div className="flex flex-col overflow-hidden rounded-md">
                    <button
                      onClick={() => verschieben(feld.id, -1)}
                      disabled={index === 0}
                      className="p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-30 dark:text-stone-500 dark:hover:bg-stone-800 dark:hover:text-stone-300"
                      aria-label="Nach oben"
                    >
                      <ChevronUp size={14} />
                    </button>
                    <button
                      onClick={() => verschieben(feld.id, 1)}
                      disabled={index === felder.length - 1}
                      className="p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-30 dark:text-stone-500 dark:hover:bg-stone-800 dark:hover:text-stone-300"
                      aria-label="Nach unten"
                    >
                      <ChevronDown size={14} />
                    </button>
                  </div>
                  <button
                    onClick={() => setBearbeitenId(feld.id)}
                    className="btn-touch rounded-md p-1.5 text-slate-400 hover:text-cyan-600 dark:text-stone-500 dark:hover:text-cyan-400"
                    aria-label="Bearbeiten"
                  >
                    <Pencil size={15} />
                  </button>
                  <button
                    onClick={() => {
                      if (window.confirm(`Feld "${feld.label}" wirklich entfernen?`)) {
                        deleteFeldMutation.mutate(feld.id);
                      }
                    }}
                    className="btn-touch rounded-md p-1.5 text-slate-400 hover:text-red-600 dark:text-stone-500 dark:hover:text-red-400"
                    aria-label="Entfernen"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            ),
          )}
        </div>

        {(updateFeldMutation.isError || createFeldMutation.isError) && (
          <p className="mt-2 text-sm text-red-600 dark:text-red-400">
            {fehlerText(updateFeldMutation.error ?? createFeldMutation.error)}
          </p>
        )}

        <div className="mt-3">
          {neuesFeldOffen ? (
            <FeldForm
              submitLabel="Feld hinzufügen"
              isPending={createFeldMutation.isPending}
              onCancel={() => setNeuesFeldOffen(false)}
              onSubmit={(values) => createFeldMutation.mutate(values)}
            />
          ) : (
            <button
              onClick={() => setNeuesFeldOffen(true)}
              className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md bg-slate-100 py-2 text-sm font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300"
            >
              <Plus size={15} /> Feld hinzufügen
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
