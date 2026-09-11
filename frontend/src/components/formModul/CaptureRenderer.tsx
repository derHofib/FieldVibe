// Erfassungs-Ansicht einer form_submission: rendert Root-Felder,
// Wiederholgruppen (mit Zeilen hinzufuegen/entfernen) und
// Praesentationselemente (nur "heading" -- die einzige Art, die aus dem
// Backfill (Migration 0077) entsteht und fuer die capture-View sinnvoll
// ist) in ihrer urspruenglichen Reihenfolge, wendet formLogicEngine.ts auf
// die aktuellen Werte an (dieselbe Engine wie das Backend beim Abschluss,
// siehe form_logic_engine.py + die geteilten Fixtures unter
// shared/form-logic-fixtures/) und ruft bei jeder Aenderung onChange mit
// dem VOLLSTAENDIGEN neuen values-Objekt auf -- Persistenz (Autosave/
// Abschliessen) ist Sache der aufrufenden Seite, nicht dieser Komponente.
import { Plus, Trash2 } from "lucide-react";
import { useMemo } from "react";

import { applyRules } from "../../utils/formLogicEngine";
import type { FormField, FormGroup, FormLogicRule, FormPresentationElement } from "../../types";
import { FormFieldRenderer } from "./FormFieldRenderer";

interface CaptureRendererProps {
  fields: FormField[];
  groups: FormGroup[];
  rules: FormLogicRule[];
  elements: FormPresentationElement[];
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
  readOnly?: boolean;
  viewId?: string | null;
  onUpload?: (fieldKey: string, file: Blob, filename: string) => void;
  hochladenPending?: boolean;
}

type Eintrag =
  | { art: "feld"; reihenfolge: number; feld: FormField }
  | { art: "element"; reihenfolge: number; element: FormPresentationElement }
  | { art: "gruppe"; reihenfolge: number; gruppe: FormGroup; felder: FormField[] };

export function CaptureRenderer({
  fields,
  groups,
  rules,
  elements,
  values,
  onChange,
  readOnly = false,
  viewId = null,
  onUpload,
  hochladenPending,
}: CaptureRendererProps) {
  const { states } = useMemo(
    () =>
      applyRules({
        fields: fields.map((f) => ({ key: f.key, group_key: f.group_key })),
        groups: groups.map((g) => ({ key: g.key })),
        rules,
        values,
        viewId,
      }),
    [fields, groups, rules, values, viewId],
  );

  const eintraege: Eintrag[] = [
    ...fields.filter((f) => f.group_key === null).map((feld) => ({ art: "feld" as const, reihenfolge: feld.reihenfolge, feld })),
    ...elements.map((element) => ({ art: "element" as const, reihenfolge: element.reihenfolge, element })),
    ...groups.map((gruppe) => ({
      art: "gruppe" as const,
      reihenfolge: gruppe.reihenfolge,
      gruppe,
      felder: fields.filter((f) => f.group_key === gruppe.key).sort((a, b) => a.reihenfolge - b.reihenfolge),
    })),
  ].sort((a, b) => a.reihenfolge - b.reihenfolge);

  function setFeldWert(key: string, wert: unknown) {
    onChange({ ...values, [key]: wert });
  }

  function setGruppenZeile(groupKey: string, index: number, feldKey: string, wert: unknown) {
    const zeilen = Array.isArray(values[groupKey]) ? [...(values[groupKey] as Record<string, unknown>[])] : [];
    zeilen[index] = { ...zeilen[index], [feldKey]: wert };
    onChange({ ...values, [groupKey]: zeilen });
  }

  function zeileHinzufuegen(groupKey: string) {
    const zeilen = Array.isArray(values[groupKey]) ? [...(values[groupKey] as Record<string, unknown>[])] : [];
    onChange({ ...values, [groupKey]: [...zeilen, {}] });
  }

  function zeileEntfernen(groupKey: string, index: number) {
    const zeilen = Array.isArray(values[groupKey]) ? [...(values[groupKey] as Record<string, unknown>[])] : [];
    zeilen.splice(index, 1);
    onChange({ ...values, [groupKey]: zeilen });
  }

  return (
    <div className="space-y-2.5">
      {eintraege.map((eintrag) => {
        if (eintrag.art === "element") {
          if (eintrag.element.type !== "heading") return null;
          const inhalt = eintrag.element.inhalt as { text?: { de?: string } };
          return (
            <h3 key={eintrag.element.id} className="pt-2 text-base font-semibold text-ind-ink">
              {inhalt.text?.de ?? ""}
            </h3>
          );
        }

        if (eintrag.art === "feld") {
          const state = states.get(eintrag.feld.key);
          if (state && !state.visible) return null;
          return (
            <FormFieldRenderer
              key={eintrag.feld.id}
              field={eintrag.feld}
              value={values[eintrag.feld.key]}
              onChange={(v) => setFeldWert(eintrag.feld.key, v)}
              readOnly={readOnly || Boolean(state?.readonly)}
              required={eintrag.feld.pflichtfeld || Boolean(state?.required)}
              onUpload={onUpload}
              hochladenPending={hochladenPending}
            />
          );
        }

        const gruppenState = states.get(eintrag.gruppe.key);
        if (gruppenState && !gruppenState.visible) return null;
        const zeilen = Array.isArray(values[eintrag.gruppe.key]) ? (values[eintrag.gruppe.key] as Record<string, unknown>[]) : [];
        const label = eintrag.gruppe.label.de ?? eintrag.gruppe.key;

        // Abschnitt (repeatable=false): genau ein Block ohne Zeilen-
        // Steuerung -- Werte liegen technisch trotzdem als values[key][0]
        // (dieselbe Speicherform wie ein Unterformular mit einer Zeile),
        // das spart eigene Auswertungslogik in form_logic_engine/-.ts.
        if (!eintrag.gruppe.repeatable) {
          const zeile = zeilen[0] ?? {};
          return (
            <div key={eintrag.gruppe.id} className="space-y-2 border border-ind-line-2 p-2">
              <h3 className="text-sm font-semibold text-ind-ink">{label}</h3>
              {eintrag.felder.map((feld) => {
                const path = `${eintrag.gruppe.key}[0].${feld.key}`;
                const state = states.get(path);
                if (state && !state.visible) return null;
                return (
                  <FormFieldRenderer
                    key={feld.id}
                    field={feld}
                    value={zeile[feld.key]}
                    onChange={(v) => setGruppenZeile(eintrag.gruppe.key, 0, feld.key, v)}
                    readOnly={readOnly || Boolean(state?.readonly)}
                    required={feld.pflichtfeld || Boolean(state?.required)}
                  />
                );
              })}
            </div>
          );
        }

        return (
          <div key={eintrag.gruppe.id} className="space-y-2 border border-ind-line-2 p-2">
            <h3 className="text-sm font-semibold text-ind-ink">{label}</h3>
            {zeilen.map((zeile, index) => (
              <div key={index} className="space-y-2 border border-ind-line bg-ind-bg-2 p-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-ind-ink-3">Eintrag {index + 1}</span>
                  {!readOnly && (
                    <button
                      type="button"
                      onClick={() => zeileEntfernen(eintrag.gruppe.key, index)}
                      className="btn-touch rounded-md p-1 text-ind-ink-3 hover:text-rose-600"
                      aria-label="Eintrag entfernen"
                    >
                      <Trash2 size={15} />
                    </button>
                  )}
                </div>
                {eintrag.felder.map((feld) => {
                  const path = `${eintrag.gruppe.key}[${index}].${feld.key}`;
                  const state = states.get(path);
                  if (state && !state.visible) return null;
                  return (
                    <FormFieldRenderer
                      key={feld.id}
                      field={feld}
                      value={zeile[feld.key]}
                      onChange={(v) => setGruppenZeile(eintrag.gruppe.key, index, feld.key, v)}
                      readOnly={readOnly || Boolean(state?.readonly)}
                      required={feld.pflichtfeld || Boolean(state?.required)}
                    />
                  );
                })}
              </div>
            ))}
            {!readOnly && (
              <button
                type="button"
                onClick={() => zeileHinzufuegen(eintrag.gruppe.key)}
                className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md bg-slate-100 py-1.5 text-sm font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300"
              >
                <Plus size={15} /> Eintrag hinzufügen
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
