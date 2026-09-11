// Editor fuer ein Formular-Modul-v2-Schema: Felder/Gruppen, Views, Regeln
// und Auftragstyp-Zuordnungen verwalten. Der Felder-Tab ist ein visueller
// WYSIWYG-Drag&Drop-Builder (siehe FormBuilderCanvas.tsx) -- Kategorien-
// Palette links, Formular-Vorschau in der Mitte, feste Eigenschaften-Spalte
// rechts. Positionierung je VIEW (Druck/PDF) passiert weiterhin ueber
// "Layout automatisch aus Feldern übernehmen" (stapelt alle Root-Felder der
// Reihe nach), nicht per Maus -- das ist ein eigenes Thema (Seiten-Layout
// fuer den Druck) und unabhaengig von der Feld-Reihenfolge im Canvas.
//
// Bewusst in drei Tabs aufgeteilt (Felder / Visualisierung / Zuordnungen)
// statt einer langen Seite mit allem untereinander -- das Anlegen eines
// Formulars soll sich auf jeweils EIN Thema konzentrieren koennen. Regeln
// sind dabei kein eigener Tab mehr, sondern haengen direkt am jeweiligen
// Feld/an der jeweiligen Gruppe (Button "Regeln" oeffnet ein SeitenPanel,
// vorbefuellt mit diesem Ziel) -- eine globale Regel-Liste ohne Bezug zum
// gerade bearbeiteten Feld war unuebersichtlich, sobald ein Schema mehr als
// eine Handvoll Regeln hatte.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { formModulApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FormBuilderCanvas } from "../../components/formModul/FormBuilderCanvas";
import { FieldValueInput, RuleConditionBuilder } from "../../components/formModul/RuleConditionBuilder";
import { FormulaBuilder } from "../../components/formModul/FormulaBuilder";
import { SeitenPanel } from "../../components/SeitenPanel";
import type { FormLogicEffekt, FormLogicRule, FormSchemaDetail, FormView, FormViewTyp, Leistungstyp } from "../../types";
import { LEISTUNGSTYP_LABEL } from "../../utils/formular";
import { describeCondition } from "../../utils/ruleConditionBuilder";

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
 * (RuleConditionBuilder) nur einmal gepflegt werden muss. festesZiel wird
 * aus dem Feld/der Gruppe uebernommen, ueber die dieses Formular geoeffnet
 * wurde -- kein Ziel-Dropdown mehr noetig, das Formular sitzt bereits im
 * Regeln-Panel genau dieses Ziels. */
function RegelForm({
  schema,
  views,
  initial,
  festesZiel,
  onSubmit,
  onCancel,
  submitting,
  error,
}: {
  schema: FormSchemaDetail;
  views: FormView[];
  initial: FormLogicRule | null;
  festesZiel: string;
  onSubmit: (payload: RegelFormPayload) => void;
  onCancel?: () => void;
  submitting: boolean;
  error: string | null;
}) {
  const [effect, setEffect] = useState<FormLogicEffekt>(initial?.effect ?? "show");
  const [condition, setCondition] = useState<unknown>(initial?.condition ?? true);
  const [value, setValue] = useState<unknown>(initial?.value ?? "");
  const [viewId, setViewId] = useState(initial?.view_id ?? "");
  // Formel-Werte sind immer Objekte ({var:...} oder {"+": [...]} etc.) --
  // ein "fester Wert" ist dagegen immer ein primitives Literal (String/
  // Zahl/Bool). Reicht als Heuristik, um beim Bearbeiten einer bestehenden
  // Regel den richtigen Reiter vorzuwaehlen.
  const [wertModus, setWertModus] = useState<"fest" | "formel">(() =>
    typeof initial?.value === "object" && initial.value !== null ? "formel" : "fest",
  );

  const zielFeld = schema.fields.find((f) => f.key === festesZiel);
  const istZielNumerisch = zielFeld?.feld_typ === "zahl" || zielFeld?.feld_typ === "betrag";

  return (
    <div className="space-y-2 border border-ind-line-2 p-3">
      <select value={effect} onChange={(e) => setEffect(e.target.value as FormLogicEffekt)} className={inputClass}>
        {(Object.keys(EFFEKT_LABEL) as FormLogicEffekt[]).map((e) => (
          <option key={e} value={e}>
            {EFFEKT_LABEL[e]}
          </option>
        ))}
      </select>

      <RuleConditionBuilder fields={schema.fields} condition={condition} onChange={setCondition} />

      {effect === "set_value" && (
        <div>
          <div className="mb-1 flex items-center justify-between">
            <label className="block text-xs font-medium text-ind-ink-2">Zu setzender Wert</label>
            {istZielNumerisch && (
              <div className="flex border border-ind-line text-[11px] font-medium">
                <button
                  type="button"
                  onClick={() => {
                    setWertModus("fest");
                    setValue("");
                  }}
                  className={`px-2 py-0.5 ${wertModus === "fest" ? "bg-ind-field text-ind-field-ink" : "text-ind-ink-3 hover:bg-ind-hover"}`}
                >
                  Fester Wert
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setWertModus("formel");
                    setValue(null);
                  }}
                  className={`px-2 py-0.5 ${wertModus === "formel" ? "bg-ind-field text-ind-field-ink" : "text-ind-ink-3 hover:bg-ind-hover"}`}
                >
                  Formel
                </button>
              </div>
            )}
          </div>
          {wertModus === "formel" && istZielNumerisch ? (
            <FormulaBuilder fields={schema.fields} value={value} onChange={setValue} />
          ) : (
            <FieldValueInput feld={zielFeld} value={value} onChange={setValue} />
          )}
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
          <button type="button" onClick={onCancel} className="btn-touch btn-industry btn-industry-secondary px-3 py-1.5 text-sm">
            Abbrechen
          </button>
        )}
        <button
          type="button"
          onClick={() =>
            onSubmit({
              target_key: festesZiel,
              effect,
              condition,
              value: effect === "set_value" ? value : undefined,
              view_id: viewId || null,
              reihenfolge: initial?.reihenfolge ?? 0,
            })
          }
          disabled={submitting}
          className="btn-touch flex items-center gap-1.5 btn-industry btn-industry-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
        >
          <Plus size={15} /> {initial ? "Speichern" : "Regel hinzufügen"}
        </button>
      </div>
    </div>
  );
}

/** Inhalt des Regeln-SeitenPanels: alle Regeln, deren target_key auf das
 * geoeffnete Feld/die Gruppe zeigt -- Regeln anderer Ziele werden hier
 * bewusst nicht angezeigt, das Panel soll sich nur auf dieses eine Ziel
 * konzentrieren. */
function RegelnPanelInhalt({
  schema,
  views,
  targetKey,
  rules,
  createRuleMutation,
  updateRuleMutation,
  deleteRuleMutation,
  regelFehler,
  setRegelFehler,
}: {
  schema: FormSchemaDetail;
  views: FormView[];
  targetKey: string;
  rules: FormLogicRule[] | undefined;
  createRuleMutation: ReturnType<typeof useCreateRuleMutation>;
  updateRuleMutation: ReturnType<typeof useUpdateRuleMutation>;
  deleteRuleMutation: ReturnType<typeof useDeleteRuleMutation>;
  regelFehler: string | null;
  setRegelFehler: (msg: string | null) => void;
}) {
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const zielRegeln = (rules ?? []).filter((r) => r.target_key === targetKey);

  return (
    <div className="space-y-3">
      {zielRegeln.length === 0 && (
        <p className="text-sm text-ind-ink-3">Noch keine Regeln für dieses Ziel.</p>
      )}
      {zielRegeln.map((r) =>
        editingRuleId === r.id ? (
          <RegelForm
            key={r.id}
            schema={schema}
            views={views}
            initial={r}
            festesZiel={targetKey}
            submitting={updateRuleMutation.isPending}
            error={regelFehler}
            onCancel={() => {
              setEditingRuleId(null);
              setRegelFehler(null);
            }}
            onSubmit={(payload) =>
              updateRuleMutation.mutate(
                { ruleId: r.id, payload },
                { onSuccess: () => setEditingRuleId(null) },
              )
            }
          />
        ) : (
          <div key={r.id} className="flex items-center justify-between gap-2 border-b border-ind-line py-1.5 text-sm">
            <span className="min-w-0 text-ind-ink">
              {EFFEKT_LABEL[r.effect]}{" "}
              <span className="text-ind-ink-3">
                {describeCondition(r.condition, (k) => schema.fields.find((f) => f.key === k)?.label.de ?? k)}
              </span>
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
        ),
      )}
      {editingRuleId === null && (
        <RegelForm
          key="neu"
          schema={schema}
          views={views}
          initial={null}
          festesZiel={targetKey}
          submitting={createRuleMutation.isPending}
          error={regelFehler}
          onSubmit={(payload) => createRuleMutation.mutate(payload)}
        />
      )}
    </div>
  );
}

// Kleine Typ-Helfer, nur damit RegelnPanelInhalt die Mutation-Objekte
// typisieren kann, ohne sie zusaetzlich zu duplizieren.
function useCreateRuleMutation(id: string, invalidate: () => void, setRegelFehler: (m: string | null) => void) {
  return useMutation({
    mutationFn: (payload: Parameters<typeof formModulApi.createRule>[1]) => formModulApi.createRule(id, payload),
    onSuccess: () => {
      setRegelFehler(null);
      invalidate();
    },
    onError: (err) => setRegelFehler(err instanceof ApiError ? err.message : "Regel konnte nicht angelegt werden"),
  });
}
function useUpdateRuleMutation(id: string, invalidate: () => void, setRegelFehler: (m: string | null) => void) {
  return useMutation({
    mutationFn: ({ ruleId, payload }: { ruleId: string; payload: Parameters<typeof formModulApi.updateRule>[2] }) =>
      formModulApi.updateRule(id, ruleId, payload),
    onSuccess: () => {
      setRegelFehler(null);
      invalidate();
    },
    onError: (err) => setRegelFehler(err instanceof ApiError ? err.message : "Regel konnte nicht gespeichert werden"),
  });
}
function useDeleteRuleMutation(id: string, invalidate: () => void) {
  return useMutation({
    mutationFn: (ruleId: string) => formModulApi.deleteRule(id, ruleId),
    onSuccess: invalidate,
  });
}

type EditorTab = "felder" | "visualisierung" | "zuordnungen";
const TAB_LABEL: Record<EditorTab, string> = {
  felder: "Felder",
  visualisierung: "Visualisierung",
  zuordnungen: "Zuordnungen",
};

export function FormSchemaEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [fehler, setFehler] = useState<string | null>(null);
  const [tab, setTab] = useState<EditorTab>("felder");

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

  // --- Regeln (im Seitenpanel je Feld/Gruppe, siehe RegelnPanelInhalt) ---
  const [regelFehler, setRegelFehler] = useState<string | null>(null);
  const [regelnZiel, setRegelnZiel] = useState<{ key: string; label: string } | null>(null);
  const createRuleMutation = useCreateRuleMutation(id!, invalidate, setRegelFehler);
  const updateRuleMutation = useUpdateRuleMutation(id!, invalidate, setRegelFehler);
  const deleteRuleMutation = useDeleteRuleMutation(id!, invalidate);

  function regelnAnzahl(key: string): number {
    return (rules ?? []).filter((r) => r.target_key === key).length;
  }

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

      <div className="seg-industry flex border border-ind-line">
        {(Object.keys(TAB_LABEL) as EditorTab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 px-3 py-2 text-xs font-semibold ${
              tab === t ? "bg-ind-field text-ind-field-ink" : "text-ind-ink-2 hover:bg-ind-hover"
            }`}
          >
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>

      {tab === "felder" && (
        <FormBuilderCanvas
          schemaId={id!}
          schema={schema}
          regelnAnzahl={regelnAnzahl}
          onRegelnOeffnen={setRegelnZiel}
          regelnPanelOffen={regelnZiel !== null}
          invalidate={invalidate}
          setFehler={setFehler}
        />
      )}

      {tab === "visualisierung" && (
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
            <button onClick={() => createViewMutation.mutate()} disabled={!viewName.trim() || createViewMutation.isPending} className="btn-touch shrink-0 btn-industry btn-industry-secondary px-3 disabled:opacity-50">
              <Plus size={16} />
            </button>
          </div>
        </div>
      )}

      {tab === "zuordnungen" && (
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
            <button onClick={() => createZuordnungMutation.mutate()} className="btn-touch shrink-0 btn-industry btn-industry-secondary px-3">
              <Plus size={16} />
            </button>
          </div>
        </div>
      )}

      {regelnZiel && (
        <SeitenPanel
          title={`Regeln: ${regelnZiel.label}`}
          onClose={() => {
            setRegelnZiel(null);
            setRegelFehler(null);
          }}
        >
          <RegelnPanelInhalt
            schema={schema}
            views={views ?? []}
            targetKey={regelnZiel.key}
            rules={rules}
            createRuleMutation={createRuleMutation}
            updateRuleMutation={updateRuleMutation}
            deleteRuleMutation={deleteRuleMutation}
            regelFehler={regelFehler}
            setRegelFehler={setRegelFehler}
          />
        </SeitenPanel>
      )}
    </div>
  );
}
