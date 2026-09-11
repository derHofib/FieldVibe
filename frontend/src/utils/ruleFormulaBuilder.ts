// Wandelt zwischen dem JSONLogic-Ausdruck eines "Formel"-set_value (siehe
// formLogicEngine.ts:evaluateCondition -- Operatoren +/-/*// zusaetzlich zu
// var) und einem einfachen, UI-tauglichen Baukasten-Modell (Liste von
// Termen -- Feld oder Zahl-Literal --, paarweise durch einen Operator
// verbunden) hin und her. Deckt bewusst nur linksassoziative Ketten ab
// (Term1 op1 Term2 op2 Term3 ...), keine Klammerung/Operator-Prioritaet --
// alles Komplexere bleibt ueber den "Erweitert"-JSON-Modus in
// FormulaBuilder.tsx erreichbar, analog zu ruleConditionBuilder.ts.

export type FormelOperator = "+" | "-" | "*" | "/";
const ARITHMETIK_OPERATOREN: FormelOperator[] = ["+", "-", "*", "/"];

export interface FormelTerm {
  art: "feld" | "zahl";
  wert: string;
}

export interface ParsedFormel {
  terme: FormelTerm[];
  operatoren: FormelOperator[];
}

export function neuerTerm(): FormelTerm {
  return { art: "feld", wert: "" };
}

function serializeTerm(t: FormelTerm): unknown {
  return t.art === "feld" ? { var: t.wert } : Number(t.wert);
}

export function serializeFormel(parsed: ParsedFormel): unknown {
  if (parsed.terme.length === 0) return null;
  let node = serializeTerm(parsed.terme[0]);
  for (let i = 0; i < parsed.operatoren.length; i++) {
    node = { [parsed.operatoren[i]]: [node, serializeTerm(parsed.terme[i + 1])] };
  }
  return node;
}

function isVarNode(node: unknown): node is { var: string } {
  return typeof node === "object" && node !== null && typeof (node as { var?: unknown }).var === "string";
}

function alsTerm(node: unknown): FormelTerm | null {
  if (typeof node === "number") return { art: "zahl", wert: String(node) };
  if (isVarNode(node)) return { art: "feld", wert: node.var };
  return null;
}

/** Liefert null, wenn der Ausdruck nicht als linksassoziative Kette im
 * einfachen Baukasten darstellbar ist (z.B. Rechtsassoziativitaet,
 * Vergleichs-/Boolesche Operatoren, Klammerung) -- der Aufrufer faellt
 * dann auf den JSON-Modus zurueck. null/undefined (kein Wert gesetzt)
 * ergibt eine leere Termliste, kein Fallback. */
export function parseFormel(node: unknown): ParsedFormel | null {
  if (node === null || node === undefined) return { terme: [], operatoren: [] };

  const direkt = alsTerm(node);
  if (direkt) return { terme: [direkt], operatoren: [] };

  const terme: FormelTerm[] = [];
  const operatoren: FormelOperator[] = [];

  function walk(n: unknown): boolean {
    if (typeof n !== "object" || n === null || Array.isArray(n)) return false;
    const keys = Object.keys(n as Record<string, unknown>);
    if (keys.length !== 1) return false;
    const op = keys[0];
    if (!(ARITHMETIK_OPERATOREN as string[]).includes(op)) return false;
    const args = (n as Record<string, unknown>)[op];
    if (!Array.isArray(args) || args.length !== 2) return false;
    const [links, rechts] = args;
    const rechtsTerm = alsTerm(rechts);
    if (!rechtsTerm) return false;
    const linksTerm = alsTerm(links);
    if (linksTerm) {
      terme.push(linksTerm);
    } else if (!walk(links)) {
      return false;
    }
    terme.push(rechtsTerm);
    operatoren.push(op as FormelOperator);
    return true;
  }

  if (!walk(node)) return null;
  return { terme, operatoren };
}
