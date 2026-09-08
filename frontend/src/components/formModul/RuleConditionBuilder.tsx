// Visueller Regel-Baukasten fuer FormLogicRule.condition: eine Liste von
// "Feld Operator Wert"-Klauseln, per UND/ODER verknuepft, statt rohem
// JSONLogic-Text. Baut auf ruleConditionBuilder.ts (reine Umwandlungslogik,
// dort auch getestet) auf. Bedingungen, die der Baukasten nicht darstellen
// kann (Verschachtelung, Negation, Gruppen-Felder), bleiben ueber einen
// "Erweitert"-JSON-Modus erreichbar -- die Engine kann mehr, als sich
// bequem visuell abbilden laesst, das soll nicht verloren gehen.
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import type { Clause, ClauseOperator, Combinator } from "../../utils/ruleConditionBuilder";
import { newClause, parseCondition, serializeCondition } from "../../utils/ruleConditionBuilder";
import type { FormField } from "../../types";

const inputClass = "btn-touch w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink";

function operatorenFuer(feld: FormField | undefined): { operator: ClauseOperator; label: string }[] {
  if (!feld) return [{ operator: "==", label: "ist" }];
  switch (feld.feld_typ) {
    case "zahl":
    case "bewertung":
    case "datum":
      return [
        { operator: "==", label: "ist" },
        { operator: "!=", label: "ist nicht" },
        { operator: "<", label: "kleiner als" },
        { operator: "<=", label: "kleiner/gleich" },
        { operator: ">", label: "größer als" },
        { operator: ">=", label: "größer/gleich" },
      ];
    case "dropdown":
      return [
        { operator: "==", label: "ist" },
        { operator: "!=", label: "ist nicht" },
        { operator: "in", label: "ist einer von" },
      ];
    case "mehrfachauswahl":
      return [{ operator: "contains", label: "enthält" }];
    default:
      return [
        { operator: "==", label: "ist" },
        { operator: "!=", label: "ist nicht" },
      ];
  }
}

function werteOptionen(feld: FormField | undefined): string[] {
  const werte = feld?.optionen?.werte;
  return Array.isArray(werte) ? (werte as string[]) : [];
}

/** Typ-bewusstes Eingabefeld fuer einen einzelnen Skalarwert -- verwendet
 * sowohl fuer Klausel-Werte (Operator != "in") als auch fuer den
 * set_value-Zielwert einer Regel (siehe FormSchemaEditorPage.tsx), damit
 * beide Stellen bei z.B. dropdown-Feldern dieselbe Auswahlliste zeigen. */
export function FieldValueInput({
  feld,
  value,
  onChange,
}: {
  feld: FormField | undefined;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  // ja_nein hat keinen neutralen dritten Options-Wert -- ein <select> ohne
  // passende Option zeigt trotzdem "Ja" an (Browser-Fallback auf die
  // erste Option), waehrend der eigentliche Zustand noch der leere
  // Platzhalter-String aus newClause()/RegelForm waere. Ohne diesen Sync
  // wuerde eine nie angefasste ja_nein-Bedingung als Vergleich mit ""
  // gespeichert statt mit dem sichtbar ausgewaehlten "Ja".
  useEffect(() => {
    if (feld?.feld_typ === "ja_nein" && typeof value !== "boolean") {
      onChange(true);
    }
  }, [feld?.feld_typ]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!feld) {
    return <input value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} className={inputClass} />;
  }

  switch (feld.feld_typ) {
    case "ja_nein":
      return (
        <select value={String(value)} onChange={(e) => onChange(e.target.value === "true")} className={inputClass}>
          <option value="true">Ja</option>
          <option value="false">Nein</option>
        </select>
      );
    case "zahl":
    case "bewertung":
      return (
        <input
          type="number"
          value={(value as number) ?? ""}
          onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
          className={inputClass}
        />
      );
    case "datum":
      return <input type="date" value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} className={inputClass} />;
    case "dropdown":
    case "mehrfachauswahl": {
      const optionen = werteOptionen(feld);
      if (optionen.length > 0) {
        return (
          <select value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} className={inputClass}>
            <option value="">Bitte wählen…</option>
            {optionen.map((w) => (
              <option key={w} value={w}>
                {w}
              </option>
            ))}
          </select>
        );
      }
      return <input value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} className={inputClass} />;
    }
    default:
      return <input value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} className={inputClass} />;
  }
}

function ValueInput({
  feld,
  operator,
  value,
  values,
  onChangeValue,
  onChangeValues,
}: {
  feld: FormField | undefined;
  operator: ClauseOperator;
  value: unknown;
  values: unknown[];
  onChangeValue: (v: unknown) => void;
  onChangeValues: (v: unknown[]) => void;
}) {
  if (operator === "in") {
    const optionen = werteOptionen(feld);
    if (optionen.length > 0) {
      return (
        <select
          multiple
          value={values as string[]}
          onChange={(e) => onChangeValues(Array.from(e.target.selectedOptions, (o) => o.value))}
          className={`${inputClass} h-20`}
        >
          {optionen.map((w) => (
            <option key={w} value={w}>
              {w}
            </option>
          ))}
        </select>
      );
    }
    return (
      <input
        value={(values as string[]).join(", ")}
        onChange={(e) => onChangeValues(e.target.value.split(",").map((v) => v.trim()).filter(Boolean))}
        placeholder="Werte, kommagetrennt"
        className={inputClass}
      />
    );
  }

  return <FieldValueInput feld={feld} value={value} onChange={onChangeValue} />;
}

interface RuleConditionBuilderProps {
  fields: FormField[];
  condition: unknown;
  onChange: (condition: unknown) => void;
}

/** Klausel-Felder sind bewusst auf Root-Felder beschraenkt (kein
 * group_key) -- eine Bedingung, die ein Gruppen-Feld referenziert, ergibt
 * nur innerhalb derselben Gruppe einen definierten Auswertungskontext
 * (siehe apply_rules/applyRules), das liesse sich im Baukasten leicht
 * falsch zusammenklicken. Wer das braucht, nutzt den Erweitert-Modus. */
export function RuleConditionBuilder({ fields, condition, onChange }: RuleConditionBuilderProps) {
  const rootFelder = fields.filter((f) => f.group_key === null);
  const parsed = parseCondition(condition);
  const [erweitert, setErweitert] = useState(parsed === null);
  const [rawJson, setRawJson] = useState(() => JSON.stringify(condition, null, 2));
  const [rawFehler, setRawFehler] = useState<string | null>(null);

  useEffect(() => {
    if (erweitert) setRawJson(JSON.stringify(condition, null, 2));
  }, [erweitert]); // eslint-disable-line react-hooks/exhaustive-deps

  const combinator: Combinator = parsed?.combinator ?? "and";
  const clauses: Clause[] = parsed?.clauses ?? [];

  function updateClauses(next: Clause[], nextCombinator: Combinator = combinator) {
    onChange(serializeCondition({ combinator: nextCombinator, clauses: next }));
  }

  if (erweitert) {
    return (
      <div className="space-y-1.5">
        <textarea
          value={rawJson}
          onChange={(e) => {
            setRawJson(e.target.value);
            try {
              onChange(JSON.parse(e.target.value));
              setRawFehler(null);
            } catch {
              setRawFehler("Kein gültiges JSON");
            }
          }}
          rows={3}
          className={`${inputClass} font-mono text-xs`}
        />
        {rawFehler && <p className="text-xs text-red-600 dark:text-red-400">{rawFehler}</p>}
        {parsed !== null && (
          <button type="button" onClick={() => setErweitert(false)} className="text-xs text-cyan-700 dark:text-cyan-400">
            Zurück zum Regel-Baukasten
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {clauses.length === 0 && <p className="text-xs text-ind-ink-3">Immer aktiv (keine Bedingung).</p>}
      {clauses.map((clause, idx) => {
        const feld = rootFelder.find((f) => f.key === clause.field);
        return (
          <div key={idx} className="space-y-1">
            {idx > 0 && (
              <div className="flex items-center gap-2 text-xs font-medium text-ind-ink-3">
                <select
                  value={combinator}
                  onChange={(e) => updateClauses(clauses, e.target.value as Combinator)}
                  className="border border-ind-line bg-transparent px-1 py-0.5"
                >
                  <option value="and">UND</option>
                  <option value="or">ODER</option>
                </select>
              </div>
            )}
            <div className="grid grid-cols-[1fr_1fr_1fr_auto] gap-1.5">
              <select
                value={clause.field}
                onChange={(e) => {
                  const next = [...clauses];
                  next[idx] = newClause(e.target.value);
                  updateClauses(next);
                }}
                className={inputClass}
              >
                <option value="">Feld wählen…</option>
                {rootFelder.map((f) => (
                  <option key={f.key} value={f.key}>
                    {f.label.de ?? f.key}
                  </option>
                ))}
              </select>
              <select
                value={clause.operator}
                onChange={(e) => {
                  const next = [...clauses];
                  next[idx] = { ...clause, operator: e.target.value as ClauseOperator, value: "", values: [] };
                  updateClauses(next);
                }}
                className={inputClass}
              >
                {operatorenFuer(feld).map((o) => (
                  <option key={o.operator} value={o.operator}>
                    {o.label}
                  </option>
                ))}
              </select>
              <ValueInput
                feld={feld}
                operator={clause.operator}
                value={clause.value}
                values={clause.values}
                onChangeValue={(v) => {
                  const next = [...clauses];
                  next[idx] = { ...clause, value: v };
                  updateClauses(next);
                }}
                onChangeValues={(v) => {
                  const next = [...clauses];
                  next[idx] = { ...clause, values: v };
                  updateClauses(next);
                }}
              />
              <button
                type="button"
                onClick={() => updateClauses(clauses.filter((_, i) => i !== idx))}
                className="btn-touch rounded-md p-1.5 text-ind-ink-3 hover:text-rose-600"
                aria-label="Bedingung entfernen"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        );
      })}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => updateClauses([...clauses, newClause(rootFelder[0]?.key ?? "")])}
          disabled={rootFelder.length === 0}
          className="btn-touch flex items-center gap-1 text-xs font-medium text-cyan-700 disabled:opacity-50 dark:text-cyan-400"
        >
          <Plus size={13} /> Bedingung
        </button>
        <button type="button" onClick={() => setErweitert(true)} className="text-xs text-ind-ink-3">
          Erweitert (JSON)
        </button>
      </div>
    </div>
  );
}
