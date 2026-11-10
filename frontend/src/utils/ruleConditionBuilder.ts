// Wandelt zwischen der JSONLogic-Bedingung einer FormLogicRule (siehe
// formLogicEngine.ts / form_logic_engine.py) und einem einfachen,
// UI-taublichen Baukasten-Modell (Liste von "Feld Operator Wert"-Klauseln,
// per UND/ODER verknuepft) hin und her. Deckt bewusst nur die haeufigen
// Faelle ab (eine Verknuepfungs-Ebene, Klausel-Felder sind Root-Felder des
// Schemas) -- alles Komplexere (Verschachtelung, Gruppen-Felder in der
// Bedingung) bleibt ueber den "Erweitert"-JSON-Modus in RuleConditionBuilder
// erreichbar, die Engine selbst kann das weiterhin.

export type ClauseOperator = "==" | "!=" | "<" | "<=" | ">" | ">=" | "in" | "contains";
export type Combinator = "and" | "or";

export interface Clause {
  field: string;
  operator: ClauseOperator;
  value: unknown;
  values: unknown[];
}

export interface ParsedCondition {
  combinator: Combinator;
  clauses: Clause[];
}

const COMPARATORS: ClauseOperator[] = ["==", "!=", "<", "<=", ">", ">="];

function isPlainValue(v: unknown): boolean {
  return v === null || typeof v === "string" || typeof v === "number" || typeof v === "boolean";
}

function isVarNode(node: unknown, field?: string): node is { var: string } {
  return (
    typeof node === "object" &&
    node !== null &&
    "var" in node &&
    typeof (node as { var: unknown }).var === "string" &&
    (field === undefined || (node as { var: string }).var === field)
  );
}

export function newClause(field: string): Clause {
  return { field, operator: "==", value: "", values: [] };
}

export function serializeClause(c: Clause): unknown {
  if (c.operator === "contains") {
    return { in: [c.value, { var: c.field }] };
  }
  if (c.operator === "in") {
    return { in: [{ var: c.field }, c.values] };
  }
  return { [c.operator]: [{ var: c.field }, c.value] };
}

export function serializeCondition(parsed: ParsedCondition): unknown {
  if (parsed.clauses.length === 0) return true;
  if (parsed.clauses.length === 1) return serializeClause(parsed.clauses[0]);
  return { [parsed.combinator]: parsed.clauses.map(serializeClause) };
}

function parseClause(node: unknown): Clause | null {
  if (typeof node !== "object" || node === null) return null;
  const keys = Object.keys(node as Record<string, unknown>);
  if (keys.length !== 1) return null;
  const op = keys[0];
  const args = (node as Record<string, unknown>)[op];
  if (!Array.isArray(args) || args.length !== 2) return null;
  const [a, b] = args;

  if (op === "in") {
    if (isVarNode(a) && Array.isArray(b)) {
      return { field: a.var, operator: "in", value: "", values: b };
    }
    if (isPlainValue(a) && isVarNode(b)) {
      return { field: b.var, operator: "contains", value: a, values: [] };
    }
    return null;
  }
  if ((COMPARATORS as string[]).includes(op) && isVarNode(a) && isPlainValue(b)) {
    return { field: a.var, operator: op as ClauseOperator, value: b, values: [] };
  }
  return null;
}

/** Liefert null, wenn die Bedingung nicht im einfachen Baukasten
 * darstellbar ist (z.B. handgeschriebenes JSON mit Verschachtelung,
 * Negation, Gruppen-Feldern) -- der Aufrufer faellt dann auf den
 * JSON-Modus zurueck. */
export function parseCondition(condition: unknown): ParsedCondition | null {
  if (condition === true) return { combinator: "and", clauses: [] };

  if (typeof condition === "object" && condition !== null) {
    const keys = Object.keys(condition as Record<string, unknown>);
    if (keys.length === 1 && (keys[0] === "and" || keys[0] === "or")) {
      const args = (condition as Record<string, unknown>)[keys[0]];
      if (Array.isArray(args)) {
        const clauses = args.map(parseClause);
        if (clauses.every((c): c is Clause => c !== null)) {
          return { combinator: keys[0] as Combinator, clauses };
        }
      }
      return null;
    }
  }

  const single = parseClause(condition);
  if (single) return { combinator: "and", clauses: [single] };
  return null;
}

const OPERATOR_LABEL: Record<ClauseOperator, string> = {
  "==": "ist",
  "!=": "ist nicht",
  "<": "kleiner als",
  "<=": "kleiner/gleich",
  ">": "größer als",
  ">=": "größer/gleich",
  in: "ist einer von",
  contains: "enthält",
};

/** Menschenlesbare Kurzbeschreibung einer Bedingung fuer die Regel-Liste im
 * Editor, z.B. "Leistungstyp ist wartung UND Zustand ist nicht gut". Faellt
 * bei nicht darstellbaren Bedingungen auf eine JSON-Kurzform zurueck. */
export function describeCondition(
  condition: unknown,
  fieldLabel: (key: string) => string,
): string {
  if (condition === true) return "immer";
  const parsed = parseCondition(condition);
  if (parsed === null) return JSON.stringify(condition);
  if (parsed.clauses.length === 0) return "immer";
  const anzeigeWert = (v: unknown): string => {
    if (typeof v === "boolean") return v ? "Ja" : "Nein";
    return String(v);
  };
  const teile = parsed.clauses.map((c) => {
    const wert = c.operator === "in" ? c.values.join(", ") : anzeigeWert(c.value);
    return `${fieldLabel(c.field)} ${OPERATOR_LABEL[c.operator]} ${wert}`;
  });
  return teile.join(parsed.combinator === "and" ? " UND " : " ODER ");
}
