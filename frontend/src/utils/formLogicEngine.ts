// Regelbasierte Logik-Engine fuer FormLogicRule (Formular-Modul v2) --
// TypeScript-Pendant zu backend/app/services/form_logic_engine.py. Wertet
// dieselbe kleine, JSONLogic-aehnliche Ausdruckssprache aus (var/
// Vergleiche/and/or/!/in) -- kein `eval`, kein Fremdcode, siehe Nicht-Ziel
// "keine freie JS-Ausfuehrung in Regeln" aus dem Migrationsplan.
//
// Beide Implementierungen werden gegen dieselben Fixtures unter
// shared/form-logic-fixtures/ getestet (siehe formLogicEngine.test.ts bzw.
// tests/test_form_logic_engine.py), damit eine Sichtbarkeitsregel
// nachweisbar in Frontend und Backend identisch entscheidet.

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export class FormLogicError extends Error {}
export class FormLogicCycleError extends Error {}

const COMPARATORS: Record<string, (a: unknown, b: unknown) => boolean> = {
  "==": (a, b) => a === b,
  "!=": (a, b) => a !== b,
  "<": (a, b) => (a as number) < (b as number),
  "<=": (a, b) => (a as number) <= (b as number),
  ">": (a, b) => (a as number) > (b as number),
  ">=": (a, b) => (a as number) >= (b as number),
};

function isPlainObject(node: unknown): node is Record<string, unknown> {
  return typeof node === "object" && node !== null && !Array.isArray(node);
}

export function evaluateCondition(node: unknown, context: Record<string, unknown>): unknown {
  if (node === null || typeof node === "boolean" || typeof node === "number" || typeof node === "string") {
    return node;
  }
  if (Array.isArray(node)) {
    return node.map((n) => evaluateCondition(n, context));
  }
  if (!isPlainObject(node)) {
    throw new FormLogicError(`Ungueltiger Ausdrucks-Knoten: ${JSON.stringify(node)}`);
  }
  const keys = Object.keys(node);
  if (keys.length !== 1) {
    throw new FormLogicError(`Jeder Ausdrucks-Knoten braucht genau einen Operator: ${JSON.stringify(node)}`);
  }
  const op = keys[0];
  const args = node[op];

  if (op === "var") {
    const path = typeof args === "string" ? args : Array.isArray(args) && args.length > 0 ? String(args[0]) : "";
    return context[path];
  }
  if (op in COMPARATORS) {
    if (!Array.isArray(args) || args.length !== 2) {
      throw new FormLogicError(`Operator '${op}' braucht genau zwei Argumente: ${JSON.stringify(args)}`);
    }
    const [a, b] = args;
    return COMPARATORS[op](evaluateCondition(a, context), evaluateCondition(b, context));
  }
  if (op === "and") {
    if (!Array.isArray(args)) {
      throw new FormLogicError(`Operator 'and' braucht eine Liste: ${JSON.stringify(args)}`);
    }
    return args.every((a) => evaluateCondition(a, context));
  }
  if (op === "or") {
    if (!Array.isArray(args)) {
      throw new FormLogicError(`Operator 'or' braucht eine Liste: ${JSON.stringify(args)}`);
    }
    return args.some((a) => evaluateCondition(a, context));
  }
  if (op === "!" || op === "not") {
    const target = Array.isArray(args) ? args[0] : args;
    return !evaluateCondition(target, context);
  }
  if (op === "in") {
    if (!Array.isArray(args) || args.length !== 2) {
      throw new FormLogicError(`Operator 'in' braucht genau zwei Argumente: ${JSON.stringify(args)}`);
    }
    const [needleRaw, haystackRaw] = args;
    const needle = evaluateCondition(needleRaw, context);
    const haystack = evaluateCondition(haystackRaw, context);
    if (typeof haystack === "string") return haystack.includes(String(needle));
    if (Array.isArray(haystack)) return haystack.includes(needle);
    throw new FormLogicError(`Operator 'in' braucht eine Liste oder einen String als zweites Argument`);
  }

  throw new FormLogicError(`Unbekannter Operator: ${op}`);
}

export function evaluateBool(node: unknown, context: Record<string, unknown>): boolean {
  return Boolean(evaluateCondition(node, context));
}

function extractVars(node: unknown): Set<string> {
  const found = new Set<string>();
  const walk = (n: unknown): void => {
    if (isPlainObject(n)) {
      if (typeof n.var === "string") found.add(n.var);
      for (const v of Object.values(n)) walk(v);
    } else if (Array.isArray(n)) {
      for (const v of n) walk(v);
    }
  };
  walk(node);
  return found;
}

export interface LogicRule {
  target_key: string;
  effect: "show" | "hide" | "require" | "readonly" | "set_value";
  condition: unknown;
  value?: unknown;
  view_id?: string | null;
  reihenfolge?: number;
}

/** Findet zyklische Abhaengigkeiten zwischen set_value-Regeln, siehe
 * detect_cycles in form_logic_engine.py fuer die vollstaendige Erklaerung. */
export function detectCycles(rules: LogicRule[]): void {
  const setValueTargets = new Set(rules.filter((r) => r.effect === "set_value").map((r) => r.target_key));
  const graph = new Map<string, Set<string>>();
  for (const t of setValueTargets) graph.set(t, new Set());

  for (const r of rules) {
    if (r.effect !== "set_value") continue;
    const referenced = new Set([...extractVars(r.condition), ...extractVars(r.value)]);
    for (const v of referenced) {
      if (setValueTargets.has(v) && v !== r.target_key) {
        graph.get(r.target_key)!.add(v);
      }
    }
  }

  const WHITE = 0;
  const GRAY = 1;
  const BLACK = 2;
  const color = new Map<string, number>();
  for (const n of graph.keys()) color.set(n, WHITE);

  const visit = (n: string, stack: string[]): void => {
    color.set(n, GRAY);
    stack.push(n);
    for (const next of graph.get(n)!) {
      if (color.get(next) === GRAY) {
        const idx = stack.indexOf(next);
        const cycle = [...stack.slice(idx), next];
        throw new FormLogicCycleError(
          `Zyklische set_value-Abhaengigkeit zwischen Feldern: ${cycle.join(" -> ")}`
        );
      }
      if (color.get(next) === WHITE) visit(next, stack);
    }
    stack.pop();
    color.set(n, BLACK);
  };

  for (const n of graph.keys()) {
    if (color.get(n) === WHITE) visit(n, []);
  }
}

export interface FieldState {
  visible: boolean;
  required: boolean;
  readonly: boolean;
}

function defaultFieldState(): FieldState {
  return { visible: true, required: false, readonly: false };
}

function applyEffect(states: Map<string, FieldState>, path: string, effect: LogicRule["effect"], active: boolean): void {
  const st = states.get(path) ?? defaultFieldState();
  if (effect === "show") st.visible = active;
  else if (effect === "hide") st.visible = !active;
  else if (effect === "require") st.required = active;
  else if (effect === "readonly") st.readonly = active;
  states.set(path, st);
}

export interface FieldDef {
  key: string;
  group_key?: string | null;
}

export interface GroupDef {
  key: string;
}

export interface RuleApplicationResult {
  states: Map<string, FieldState>;
  values: Record<string, unknown>;
}

/** Wendet alle fuer `viewId` geltenden Regeln auf `values` an -- siehe
 * apply_rules in form_logic_engine.py fuer die vollstaendige Erklaerung der
 * View-Scoping-, Gruppen- und Reihenfolge-Semantik (beide Implementierungen
 * muessen sich identisch verhalten, siehe die geteilten Test-Fixtures). */
export function applyRules(args: {
  fields: FieldDef[];
  groups: GroupDef[];
  rules: LogicRule[];
  values: Record<string, unknown>;
  viewId?: string | null;
}): RuleApplicationResult {
  const { fields, groups, rules, values, viewId = null } = args;
  detectCycles(rules);

  const workingValues: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(values)) {
    workingValues[k] = Array.isArray(v) ? v.map((row) => ({ ...(row as Record<string, unknown>) })) : v;
  }

  const fieldGroupOf = new Map(fields.map((f) => [f.key, f.group_key ?? null]));
  const groupKeys = new Set(groups.map((g) => g.key));

  const applicable = rules
    .filter((r) => r.view_id === undefined || r.view_id === null || r.view_id === viewId)
    .slice()
    .sort((a, b) => (a.reihenfolge ?? 0) - (b.reihenfolge ?? 0));

  const states = new Map<string, FieldState>();

  for (const rule of applicable) {
    const target = rule.target_key;

    if (groupKeys.has(target)) {
      const active = evaluateBool(rule.condition, workingValues);
      applyEffect(states, target, rule.effect, active);
      continue;
    }

    const groupKey = fieldGroupOf.get(target) ?? null;
    if (groupKey === null) {
      const active = evaluateBool(rule.condition, workingValues);
      if (rule.effect === "set_value") {
        if (active) workingValues[target] = rule.value ?? null;
      } else {
        applyEffect(states, target, rule.effect, active);
      }
      continue;
    }

    if (!Array.isArray(workingValues[groupKey])) workingValues[groupKey] = [];
    const rows = workingValues[groupKey] as Record<string, unknown>[];
    rows.forEach((row, idx) => {
      const ctx = { ...workingValues, ...row };
      const active = evaluateBool(rule.condition, ctx);
      const path = `${groupKey}[${idx}].${target}`;
      if (rule.effect === "set_value") {
        if (active) row[target] = rule.value ?? null;
      } else {
        applyEffect(states, path, rule.effect, active);
      }
    });
  }

  return { states, values: workingValues };
}
