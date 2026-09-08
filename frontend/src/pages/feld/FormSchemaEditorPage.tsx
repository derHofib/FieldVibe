// Editor fuer ein Formular-Modul-v2-Schema: Felder/Gruppen, Views, Regeln
// und Auftragstyp-Zuordnungen verwalten. Bewusst formularbasiert statt ein
// visueller Drag&Drop-Builder (siehe Nicht-Ziel im Migrationsplan) --
// Positionierung je View passiert ueber "Layout automatisch aus Feldern
// übernehmen" (stapelt alle Root-Felder der Reihe nach), nicht per Maus.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { formModulApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FieldValueInput, RuleConditionBuilder } from "../../components/formModul/RuleConditionBuilder";
import type {
  FormFeldTyp,
  FormLogicEffekt,
  FormLogicRule,
  FormSchemaDetail,
  FormView,
  FormViewTyp,
  Leistungstyp,
} from "../../types";
import { LEISTUNGSTYP_LABEL } from "../../utils/formular";
import { describeCondition } from "../../utils/ruleConditionBuilder";

const FELD_TYPEN: FormFeldTyp[] = [
  "text",
  "textarea",
  "zahl",
  "datum",
  "dropdown",
  "mehrfachauswahl",
  "ja_nein",
  "bewertung",
  "foto",
  "unterschrift",
  "gps",
  "qr_scan",
];
const VIEW_TYPEN: FormViewTyp[] = ["capture", "print", "summary", "table", "public"];
const LEISTUNGSTYPEN = Object.keys(LEISTUNGSTYP_LABEL) as Leistungstyp[];

const inputClass = "btn-touch w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink";
const sectionClass = "space-y-3 border border-ind-line bg-ind-bg p-4";

const EFFEKT_LABEL: Record<FormLogicEffekt, string> = {
  show: "Anzeigen, wenn",
  hide: "Ausblenden, wenn",
  require: "Pflicht, wenn",
  readonly: "Schreibgeschützt, wenn",
  set_value: "Wert setzen, wenn",
};

interface RegelFormPayload {
  target_key: string;
  effect: FormLogicEffekt;
  condition: unknown;
  value?: unknown;
  view_id: string | null;
  reihenfolge: number;
}

/** Formular fuer eine einzelne Regel -- gemeinsam fuer "neue Regel
 * anlegen" und "bestehende Regel bearbeiten" (initial=null bzw. die zu
 * bearbeitende Regel), damit der visuelle Bedingungs-Baukasten
 * (RuleConditionBuilder) nur einmal gepflegt werden muss. */
function RegelForm({
  schema,
  views,
  initial,
  onSubmit,
  onCancel,
  submitting,
  error,
}: {
  schema: FormSchemaDetail;
  views: FormView[];
  initial: FormLogicRule | null;
  onSubmit: (payload: RegelFormPayload) => void;
  onCancel?: () => void;
  submitting: boolean;
  error: string | null;
}) {
  const [targetKey, setTargetKey] = useState(initial?.target_key ?? "");
  const [effect, setEffect] = useState<FormLogicEffekt>(initial?.effect ?? "show");
  const [condition, setCondition] = useState<unknown>(initial?.condition ?? true);
  const [value, setValue] = useState<unknown>(initial?.value ?? "");
  const [viewId, setViewId] = useState(initial?.view_id ?? "");

  const targetOptions = [
    ...schema.fields.map((f) => ({
      key: f.key,
      label: f.group_key ? `${f.label.de ?? f.key} (in ${schema.groups.find((g) => g.key === f.group_key)?.label.de ?? f.group_key})` : f.label.de ?? f.key,
    })),
    ...schema.groups.map((g) => ({ key: g.key, label: `Gruppe: ${g.label.de ?? g.key}` })),
  ];
  const zielFeld = schema.fields.find((f) => f.key === targetKey);

  return (
    <div className="space-y-2 border border-ind-line-2 p-3">
      <div className="grid grid-cols-2 gap-2">
        <select value={targetKey} onChange={(e) => setTargetKey(e.target.value)} className={inputClass}>
          <option value="">Ziel wählen…</option>
          {targetOptions.map((o) => (
            <option key={o.key} value={o.key}>
              {o.label}
            </option>
          ))}
        </select>
        <select value={effect} onChange={(e) => setEffect(e.target.value as FormLogicEffekt)} className={inputClass}>
          {(Object.keys(EFFEKT_LABEL) as FormLogicEffekt[]).map((e) => (
            <option key={e} value={e}>
              {EFFEKT_LABEL[e]}
            </option>
          ))}
        </select>
      </div>

      <RuleConditionBuilder fields={schema.fields} condition={condition} onChange={setCondition} />

      {effect === "set_value" && (
        <div>
          <label className="mb-1 block text-xs font-medium text-ind-ink-2">Zu setzender Wert</label>
          <FieldValueInput feld={zielFeld} value={value} onChange={setValue} />
        </div>
      )}

      <div>
        <label className="mb-1 block text-xs font-medium text-ind-ink-2">Gültig in</label>
        <select value={viewId ?? ""} onChange={(e) => setViewId(e.target.value)} className={inputClass}>
          <option value="">Global (alle Views)</option>
          {views.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name} ({v.type})
            </option>
          ))}
        </select>
      </div>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <div className="flex items-center justify-end gap-2">
        {onCancel && (
          <button type="button" onClick={onCancel} className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600 dark:bg-stone-800 dark:text-stone-300">
            Abbrechen
          </button>
        )}
        <button
          type="button"
          onClick={() =>
            onSubmit({
              target_key: targetKey,
              effect,
              condition,
              value: effect === "set_value" ? value : undefined,
              view_id: viewId || null,
              reihenfolge: initial?.reihenfolge ?? 0,
            })
          }
          disabled={!targetKey || submitting}
          className="btn-touch flex items-center gap-1.5 rounded-md btn-industry btn-industry-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
        >
          <Plus size={15} /> {initial ? "Speichern" : "Regel hinzufügen"}
        </button>
      </div>
    </div>
  );
}

export function FormSchemaEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: schema, isLoading } = useQuery({
    queryKey: ["form-schema", id],
    queryFn: () => formModulApi.getSchema(id!),
    enabled: !!id,
  });
  const { data: views } = useQuery({
    queryKey: ["form-views", id],
    queryFn: () => formModulApi.listViews(id!),
    enabled: !!id,
  });
  const { data: rules } = useQuery({
    queryKey: ["form-rules", id],
    queryFn: () => formModulApi.listRules(id!),
    enabled: !!id,
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["form-schema", id] });
    queryClient.invalidateQueries({ queryKey: ["form-views", id] });
    queryClient.invalidateQueries({ queryKey: ["form-rules", id] });
  }

  const publishMutation = useMutation({
    mutationFn: () => formModulApi.updateSchema(id!, { status: "published" }),
    onSuccess: invalidate,
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Konnte nicht veröffentlicht werden"),
  });

  // --- Felder/Gruppen ---
  const [feldKey, setFeldKey] = useState("");
  const [feldLabel, setFeldLabel] = useState("");
  const [feldTyp, setFeldTyp] = useState<FormFeldTyp>("text");
  const [feldGruppe, setFeldGruppe] = useState("");
  const [gruppeKey, setGruppeKey] = useState("");
  const [gruppeLabel, setGruppeLabel] = useState("");

  const createFieldMutation = useMutation({
    mutationFn: () =>
      formModulApi.createField(id!, {
        key: feldKey.trim(),
        feld_typ: feldTyp,
        label: { de: feldLabel.trim() || feldKey.trim() },
        group_key: feldGruppe || null,
      }),
    onSuccess: () => {
      setFeldKey("");
      setFeldLabel("");
      invalidate();
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Feld konnte nicht angelegt werden"),
  });
  const deleteFieldMutation = useMutation({
    mutationFn: (fieldId: string) => formModulApi.deleteField(id!, fieldId),
    onSuccess: invalidate,
  });
  const createGroupMutation = useMutation({
    mutationFn: () => formModulApi.createGroup(id!, { key: gruppeKey.trim(), label: { de: gruppeLabel.trim() || gruppeKey.trim() } }),
    onSuccess: () => {
      setGruppeKey("");
      setGruppeLabel("");
      invalidate();
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Gruppe konnte nicht angelegt werden"),
  });
  const deleteGroupMutation = useMutation({
    mutationFn: (groupId: string) => formModulApi.deleteGroup(id!, groupId),
    onSuccess: invalidate,
  });

  // --- Views ---
  const [viewTyp, setViewTyp] = useState<FormViewTyp>("capture");
  const [viewName, setViewName] = useState("");

  const createViewMutation = useMutation({
    mutationFn: () => formModulApi.createView(id!, { type: viewTyp, name: viewName.trim() }),
    onSuccess: () => {
      setViewName("");
      invalidate();
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "View konnte nicht angelegt werden"),
  });
  const deleteViewMutation = useMutation({
    mutationFn: (viewId: string) => formModulApi.deleteView(id!, viewId),
    onSuccess: invalidate,
  });
  const autoLayoutMutation = useMutation({
    mutationFn: (viewId: string) => {
      const rootFelder = (schema?.fields ?? []).filter((f) => f.group_key === null).sort((a, b) => a.reihenfolge - b.reihenfolge);
      const layouts = rootFelder.map((f, i) => ({ field_key: f.key, seite: 0, x_mm: 0, y_mm: i * 12, breite_mm: 85, hoehe_mm: 10 }));
      return formModulApi.replaceLayouts(id!, viewId, layouts);
    },
    onSuccess: invalidate,
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Layout konnte nicht übernommen werden"),
  });

  // --- Regeln ---
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [regelFehler, setRegelFehler] = useState<string | null>(null);

  const createRuleMutation = useMutation({
    mutationFn: (payload: Parameters<typeof formModulApi.createRule>[1]) => formModulApi.createRule(id!, payload),
    onSuccess: () => {
      setRegelFehler(null);
      invalidate();
    },
    onError: (err) => setRegelFehler(err instanceof ApiError ? err.message : "Regel konnte nicht angelegt werden"),
  });
  const updateRuleMutation = useMutation({
    mutationFn: ({ ruleId, payload }: { ruleId: string; payload: Parameters<typeof formModulApi.updateRule>[2] }) =>
      formModulApi.updateRule(id!, ruleId, payload),
    onSuccess: () => {
      setRegelFehler(null);
      setEditingRuleId(null);
      invalidate();
    },
    onError: (err) => setRegelFehler(err instanceof ApiError ? err.message : "Regel konnte nicht gespeichert werden"),
  });
  const deleteRuleMutation = useMutation({
    mutationFn: (ruleId: string) => formModulApi.deleteRule(id!, ruleId),
    onSuccess: invalidate,
  });

  // --- Zuordnungen ---
  const [zuLeistungstyp, setZuLeistungstyp] = useState<Leistungstyp>("wartung");
  const [zuPflicht, setZuPflicht] = useState(false);

  const createZuordnungMutation = useMutation({
    mutationFn: () => formModulApi.createZuordnung(id!, { leistungstyp: zuLeistungstyp, pflicht_vor_abschluss: zuPflicht }),
    onSuccess: invalidate,
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Zuordnung konnte nicht angelegt werden"),
  });
  const deleteZuordnungMutation = useMutation({
    mutationFn: (zuordnungId: string) => formModulApi.deleteZuordnung(id!, zuordnungId),
    onSuccess: invalidate,
  });

  if (isLoading) return <p className="text-center text-sm text-ind-ink-3">Lädt…</p>;
  if (!schema) return <EmptyState icon={FileText} text="Schema nicht gefunden." />;

  return (
    <div className="space-y-4 pb-8">
      <button onClick={() => navigate("/form-schemas")} className="text-sm text-ind-ink-3">
        ← Zurück
      </button>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-ind-ink">{schema.name}</h1>
          <p className="text-xs text-ind-ink-3">Version {schema.version} · {schema.status}</p>
        </div>
        {schema.status === "draft" && (
          <button onClick={() => publishMutation.mutate()} disabled={publishMutation.isPending} className="btn-touch rounded-md btn-industry btn-industry-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50">
            Veröffentlichen
          </button>
        )}
      </div>
      {fehler && <p className="text-sm text-red-600 dark:text-red-400">{fehler}</p>}

      <div className={sectionClass}>
        <h2 className="text-sm font-semibold text-ind-ink">Gruppen (Wiederholbereiche)</h2>
        {schema.groups.map((g) => (
          <div key={g.id} className="flex items-center justify-between border-b border-ind-line py-1.5 text-sm">
            <span className="text-ind-ink">{g.label.de ?? g.key} <span className="text-ind-ink-3">({g.key})</span></span>
            <button onClick={() => deleteGroupMutation.mutate(g.id)} className="text-ind-ink-3 hover:text-rose-600">
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        <div className="flex gap-2">
          <input value={gruppeKey} onChange={(e) => setGruppeKey(e.target.value)} placeholder="key (z.B. maengel)" className={inputClass} />
          <input value={gruppeLabel} onChange={(e) => setGruppeLabel(e.target.value)} placeholder="Bezeichnung" className={inputClass} />
          <button onClick={() => createGroupMutation.mutate()} disabled={!gruppeKey.trim() || createGroupMutation.isPending} className="btn-touch shrink-0 rounded-md bg-slate-100 px-3 text-slate-600 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300">
            <Plus size={16} />
          </button>
        </div>
      </div>

      <div className={sectionClass}>
        <h2 className="text-sm font-semibold text-ind-ink">Felder</h2>
        {schema.fields.map((f) => (
          <div key={f.id} className="flex items-center justify-between border-b border-ind-line py-1.5 text-sm">
            <span className="text-ind-ink">
              {f.label.de ?? f.key} <span className="text-ind-ink-3">({f.key} · {f.feld_typ}{f.group_key ? ` · in ${f.group_key}` : ""})</span>
            </span>
            <button onClick={() => deleteFieldMutation.mutate(f.id)} className="text-ind-ink-3 hover:text-rose-600">
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        <div className="grid grid-cols-2 gap-2">
          <input value={feldKey} onChange={(e) => setFeldKey(e.target.value)} placeholder="key (z.B. kommentar)" className={inputClass} />
          <input value={feldLabel} onChange={(e) => setFeldLabel(e.target.value)} placeholder="Bezeichnung" className={inputClass} />
          <select value={feldTyp} onChange={(e) => setFeldTyp(e.target.value as FormFeldTyp)} className={inputClass}>
            {FELD_TYPEN.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select value={feldGruppe} onChange={(e) => setFeldGruppe(e.target.value)} className={inputClass}>
            <option value="">Kein Gruppen-Feld</option>
            {schema.groups.map((g) => (
              <option key={g.key} value={g.key}>
                {g.label.de ?? g.key}
              </option>
            ))}
          </select>
        </div>
        <button onClick={() => createFieldMutation.mutate()} disabled={!feldKey.trim() || createFieldMutation.isPending} className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md bg-slate-100 py-1.5 text-sm font-medium text-slate-600 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300">
          <Plus size={15} /> Feld hinzufügen
        </button>
      </div>

      <div className={sectionClass}>
        <h2 className="text-sm font-semibold text-ind-ink">Views</h2>
        {(views ?? []).map((v) => (
          <div key={v.id} className="flex items-center justify-between border-b border-ind-line py-1.5 text-sm">
            <span className="text-ind-ink">{v.name} <span className="text-ind-ink-3">({v.type})</span></span>
            <div className="flex items-center gap-2">
              {v.type !== "capture" ? null : (
                <button onClick={() => autoLayoutMutation.mutate(v.id)} className="text-xs text-cyan-700 dark:text-cyan-400">
                  Layout aus Feldern übernehmen
                </button>
              )}
              <button onClick={() => deleteViewMutation.mutate(v.id)} className="text-ind-ink-3 hover:text-rose-600">
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
        <div className="flex gap-2">
          <select value={viewTyp} onChange={(e) => setViewTyp(e.target.value as FormViewTyp)} className={inputClass}>
            {VIEW_TYPEN.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input value={viewName} onChange={(e) => setViewName(e.target.value)} placeholder="Name (z.B. Erfassung)" className={inputClass} />
          <button onClick={() => createViewMutation.mutate()} disabled={!viewName.trim() || createViewMutation.isPending} className="btn-touch shrink-0 rounded-md bg-slate-100 px-3 text-slate-600 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300">
            <Plus size={16} />
          </button>
        </div>
      </div>

      <div className={sectionClass}>
        <h2 className="text-sm font-semibold text-ind-ink">Regeln</h2>
        {(rules ?? []).map((r) => {
          const zielLabel =
            schema.fields.find((f) => f.key === r.target_key)?.label.de ??
            schema.groups.find((g) => g.key === r.target_key)?.label.de ??
            r.target_key;
          if (editingRuleId === r.id) {
            return (
              <RegelForm
                key={r.id}
                schema={schema}
                views={views ?? []}
                initial={r}
                submitting={updateRuleMutation.isPending}
                error={regelFehler}
                onCancel={() => {
                  setEditingRuleId(null);
                  setRegelFehler(null);
                }}
                onSubmit={(payload) => updateRuleMutation.mutate({ ruleId: r.id, payload })}
              />
            );
          }
          return (
            <div key={r.id} className="flex items-center justify-between gap-2 border-b border-ind-line py-1.5 text-sm">
              <span className="text-ind-ink">
                {EFFEKT_LABEL[r.effect]} <span className="text-ind-ink-3">{describeCondition(r.condition, (k) => schema.fields.find((f) => f.key === k)?.label.de ?? k)}</span>
                {" → "}
                {zielLabel}
                {r.effect === "set_value" && <span className="text-ind-ink-3"> = {JSON.stringify(r.value)}</span>}
              </span>
              <div className="flex shrink-0 items-center gap-2">
                <button onClick={() => setEditingRuleId(r.id)} className="text-xs text-cyan-700 dark:text-cyan-400">
                  Bearbeiten
                </button>
                <button onClick={() => deleteRuleMutation.mutate(r.id)} className="text-ind-ink-3 hover:text-rose-600">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          );
        })}
        {editingRuleId === null && (
          <RegelForm
            key="neu"
            schema={schema}
            views={views ?? []}
            initial={null}
            submitting={createRuleMutation.isPending}
            error={regelFehler}
            onSubmit={(payload) => createRuleMutation.mutate(payload)}
          />
        )}
      </div>

      <div className={sectionClass}>
        <h2 className="text-sm font-semibold text-ind-ink">Auftragstyp-Zuordnungen</h2>
        {schema.zuordnungen.map((z) => (
          <div key={z.id} className="flex items-center justify-between border-b border-ind-line py-1.5 text-sm">
            <span className="text-ind-ink">
              {LEISTUNGSTYP_LABEL[z.leistungstyp]} {z.pflicht_vor_abschluss && <span className="text-ind-ink-3">(Pflicht vor Abschluss)</span>}
            </span>
            <button onClick={() => deleteZuordnungMutation.mutate(z.id)} className="text-ind-ink-3 hover:text-rose-600">
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        <div className="flex items-center gap-2">
          <select value={zuLeistungstyp} onChange={(e) => setZuLeistungstyp(e.target.value as Leistungstyp)} className={inputClass}>
            {LEISTUNGSTYPEN.map((lt) => (
              <option key={lt} value={lt}>
                {LEISTUNGSTYP_LABEL[lt]}
              </option>
            ))}
          </select>
          <label className="flex shrink-0 items-center gap-1.5 text-xs text-ind-ink-2">
            <input type="checkbox" checked={zuPflicht} onChange={(e) => setZuPflicht(e.target.checked)} /> Pflicht
          </label>
          <button onClick={() => createZuordnungMutation.mutate()} className="btn-touch shrink-0 rounded-md bg-slate-100 px-3 text-slate-600 dark:bg-stone-800 dark:text-stone-300">
            <Plus size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
