// Visueller Formel-Baukasten fuer set_value: eine Kette aus Feld-/Zahl-
// Termen, paarweise durch +/-/x/÷ verbunden -- die "Formel kann wie eine
// Regel eingestellt werden"-Anforderung. Baut auf ruleFormulaBuilder.ts
// (reine Umwandlungslogik, dort getestet) auf, analog zu
// RuleConditionBuilder.tsx fuer Bedingungen. Formeln, die der Baukasten
// nicht darstellen kann, bleiben ueber einen "Erweitert"-JSON-Modus
// erreichbar.
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import type { FormelOperator, FormelTerm } from "../../utils/ruleFormulaBuilder";
import { neuerTerm, parseFormel, serializeFormel } from "../../utils/ruleFormulaBuilder";
import type { FormField } from "../../types";

const inputClass = "btn-touch w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink";

const OPERATOR_LABEL: Record<FormelOperator, string> = {
  "+": "+",
  "-": "−",
  "*": "×",
  "/": "÷",
};

interface FormulaBuilderProps {
  fields: FormField[];
  value: unknown;
  onChange: (value: unknown) => void;
}

/** Nur numerische Root-Felder (zahl/betrag) sind sinnvolle Formel-
 * Bausteine -- ein Formel-Ergebnis ist immer eine Zahl, siehe
 * evaluateCondition-Arithmetik in formLogicEngine.ts. */
function numerischeFelder(fields: FormField[]): FormField[] {
  return fields.filter((f) => f.group_key === null && (f.feld_typ === "zahl" || f.feld_typ === "betrag"));
}

export function FormulaBuilder({ fields, value, onChange }: FormulaBuilderProps) {
  const rootFelder = numerischeFelder(fields);
  const parsed = parseFormel(value);
  const [erweitert, setErweitert] = useState(parsed === null);
  const [rawJson, setRawJson] = useState(() => JSON.stringify(value ?? null, null, 2));
  const [rawFehler, setRawFehler] = useState<string | null>(null);

  useEffect(() => {
    if (erweitert) setRawJson(JSON.stringify(value ?? null, null, 2));
  }, [erweitert]); // eslint-disable-line react-hooks/exhaustive-deps

  const terme: FormelTerm[] = parsed?.terme ?? [];
  const operatoren: FormelOperator[] = parsed?.operatoren ?? [];

  function update(nextTerme: FormelTerm[], nextOperatoren: FormelOperator[]) {
    onChange(serializeFormel({ terme: nextTerme, operatoren: nextOperatoren }));
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
            Zurück zum Formel-Baukasten
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {terme.length === 0 && <p className="text-xs text-ind-ink-3">Kein Term -- Formel hinzufügen.</p>}
      {terme.map((term, idx) => (
        <div key={idx} className="flex items-center gap-1.5">
          {idx > 0 && (
            <select
              value={operatoren[idx - 1]}
              onChange={(e) => {
                const nextOperatoren = [...operatoren];
                nextOperatoren[idx - 1] = e.target.value as FormelOperator;
                update(terme, nextOperatoren);
              }}
              className="w-14 shrink-0 border border-ind-line bg-transparent px-1 py-1.5 text-center text-sm text-ind-ink"
            >
              {(Object.keys(OPERATOR_LABEL) as FormelOperator[]).map((op) => (
                <option key={op} value={op}>
                  {OPERATOR_LABEL[op]}
                </option>
              ))}
            </select>
          )}
          <select
            value={term.art}
            onChange={(e) => {
              const next = [...terme];
              next[idx] = { art: e.target.value as "feld" | "zahl", wert: "" };
              update(next, operatoren);
            }}
            className="w-20 shrink-0 border border-ind-line bg-transparent px-1 py-1.5 text-sm text-ind-ink"
          >
            <option value="feld">Feld</option>
            <option value="zahl">Zahl</option>
          </select>
          {term.art === "feld" ? (
            <select
              value={term.wert}
              onChange={(e) => {
                const next = [...terme];
                next[idx] = { ...term, wert: e.target.value };
                update(next, operatoren);
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
          ) : (
            <input
              type="number"
              value={term.wert}
              onChange={(e) => {
                const next = [...terme];
                next[idx] = { ...term, wert: e.target.value };
                update(next, operatoren);
              }}
              className={inputClass}
            />
          )}
          <button
            type="button"
            onClick={() => {
              // Genau EIN angrenzender Operator wird mitentfernt (rechter
              // Nachbar, falls vorhanden, sonst der linke) -- nie beide,
              // sonst wuerden benachbarte Terme ohne Verbindung zurueckbleiben.
              const opIndexZuEntfernen = idx < operatoren.length ? idx : idx - 1;
              const nextTerme = terme.filter((_, i) => i !== idx);
              const nextOperatoren = operatoren.filter((_, i) => i !== opIndexZuEntfernen);
              update(nextTerme, nextOperatoren);
            }}
            className="btn-touch shrink-0 p-1.5 text-ind-ink-3 hover:text-red-600 dark:hover:text-red-400"
            aria-label="Term entfernen"
          >
            <Trash2 size={14} strokeWidth={1.5} />
          </button>
        </div>
      ))}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => update([...terme, neuerTerm()], terme.length > 0 ? [...operatoren, "+"] : operatoren)}
          className="btn-touch flex items-center gap-1 text-xs font-medium text-cyan-700 dark:text-cyan-400"
        >
          <Plus size={13} strokeWidth={1.5} /> Term
        </button>
        <button type="button" onClick={() => setErweitert(true)} className="text-xs text-ind-ink-3">
          Erweitert (JSON)
        </button>
      </div>
    </div>
  );
}
