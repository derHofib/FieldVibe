"""Regelbasierte Logik-Engine fuer FormLogicRule (Formular-Modul v2).

Wertet eine JSONLogic-aehnliche, aber bewusst kleine Ausdruckssprache aus
(var/Vergleiche/and/or/!/in) -- kein `eval`, kein Zugriff auf Python-Objekte
ausserhalb des uebergebenen context-dict, siehe Nicht-Ziel "keine freie
JS-Ausfuehrung in Regeln" aus dem Migrationsplan.

Dieses Modul ist die Referenzimplementierung; die funktional identische
TypeScript-Variante liegt unter frontend/src/utils/formLogicEngine.ts.
Beide werden gegen dieselben Fixtures in shared/form-logic-fixtures/
getestet (siehe tests/test_form_logic_engine.py bzw. das Vitest-Pendant),
damit eine Sichtbarkeitsregel nachweisbar in Frontend und Backend
identisch entscheidet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class FormLogicError(Exception):
    """Ungueltiger/nicht unterstuetzter Ausdrucks-Knoten."""


class FormLogicCycleError(Exception):
    """Zyklische set_value-Abhaengigkeit zwischen Regeln."""


_COMPARATORS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}
_ARITHMETIK = ("+", "-", "*", "/")


def evaluate_condition(node: Any, context: dict[str, Any]) -> Any:
    """Wertet einen JSONLogic-aehnlichen Ausdrucksknoten aus.

    Unterstuetzte Operatoren: var, ==, !=, <, <=, >, >=, and, or, !/not, in.
    Literale (str/int/float/bool/None/list) werten sich selbst aus. Jeder
    andere Operator oder ein strukturell ungueltiger Knoten wirft
    FormLogicError statt still einen falschen Wert zu liefern.
    """
    if node is None or isinstance(node, (bool, int, float, str)):
        return node
    if isinstance(node, list):
        return [evaluate_condition(n, context) for n in node]
    if not isinstance(node, dict):
        raise FormLogicError(f"Ungueltiger Ausdrucks-Knoten: {node!r}")
    if len(node) != 1:
        raise FormLogicError(f"Jeder Ausdrucks-Knoten braucht genau einen Operator: {node!r}")
    (op, args), = node.items()

    if op == "var":
        path = args if isinstance(args, str) else (args[0] if args else "")
        return context.get(path)
    if op in _COMPARATORS:
        if not isinstance(args, list) or len(args) != 2:
            raise FormLogicError(f"Operator '{op}' braucht genau zwei Argumente: {args!r}")
        a, b = args
        return _COMPARATORS[op](evaluate_condition(a, context), evaluate_condition(b, context))
    if op in _ARITHMETIK:
        # Fuer Formel-Felder (set_value mit einem Ausdruck statt einem
        # Literal als value, siehe apply_rules) -- bewusst None statt eines
        # Fehlers bei fehlenden/nicht-numerischen Operanden oder
        # Division durch 0: eine unvollstaendig ausgefuellte Formel soll das
        # Formular nicht zum Absturz bringen, das Zielfeld bleibt dann leer.
        if not isinstance(args, list) or len(args) < 2:
            raise FormLogicError(f"Operator '{op}' braucht mindestens zwei Argumente: {args!r}")
        werte = [evaluate_condition(a, context) for a in args]
        if any(not isinstance(w, (int, float)) or isinstance(w, bool) for w in werte):
            return None
        ergebnis = werte[0]
        for w in werte[1:]:
            if op == "+":
                ergebnis = ergebnis + w
            elif op == "-":
                ergebnis = ergebnis - w
            elif op == "*":
                ergebnis = ergebnis * w
            elif w == 0:
                return None
            else:
                ergebnis = ergebnis / w
        return ergebnis
    if op == "and":
        if not isinstance(args, list):
            raise FormLogicError(f"Operator 'and' braucht eine Liste: {args!r}")
        return all(evaluate_condition(a, context) for a in args)
    if op == "or":
        if not isinstance(args, list):
            raise FormLogicError(f"Operator 'or' braucht eine Liste: {args!r}")
        return any(evaluate_condition(a, context) for a in args)
    if op in ("!", "not"):
        target = args[0] if isinstance(args, list) else args
        return not evaluate_condition(target, context)
    if op == "in":
        if not isinstance(args, list) or len(args) != 2:
            raise FormLogicError(f"Operator 'in' braucht genau zwei Argumente: {args!r}")
        needle, haystack = args
        return evaluate_condition(needle, context) in evaluate_condition(haystack, context)

    raise FormLogicError(f"Unbekannter Operator: {op!r}")


def evaluate_bool(node: Any, context: dict[str, Any]) -> bool:
    return bool(evaluate_condition(node, context))


def _extract_vars(node: Any) -> set[str]:
    found: set[str] = set()

    def walk(n: Any) -> None:
        if isinstance(n, dict):
            if "var" in n and isinstance(n["var"], str):
                found.add(n["var"])
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return found


def detect_cycles(rules: list[dict[str, Any]]) -> None:
    """Findet zyklische Abhaengigkeiten zwischen set_value-Regeln.

    Nur set_value-Regeln veraendern `values` waehrend der Auswertung --
    andere Effekte (show/hide/require/readonly) lesen nur, koennen also
    keinen Zyklus in der Werte-Berechnung erzeugen. Ein Zyklus liegt vor,
    wenn Regel A einen Wert X setzt, dessen Bedingung von Feld Y abhaengt,
    Y wiederum durch Regel B gesetzt wird, deren Bedingung von X abhaengt
    (oder laenger). Wird bereits beim Anlegen/Aendern einer Regel
    aufgerufen (siehe form_views-Routen, Schritt 4) sowie defensiv vor
    jeder Auswertung.
    """
    set_value_targets = {r["target_key"] for r in rules if r["effect"] == "set_value"}
    graph: dict[str, set[str]] = {t: set() for t in set_value_targets}
    for r in rules:
        if r["effect"] != "set_value":
            continue
        target = r["target_key"]
        referenced = _extract_vars(r.get("condition")) | _extract_vars(r.get("value"))
        for v in referenced:
            if v in set_value_targets and v != target:
                graph[target].add(v)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}

    def visit(n: str, stack: list[str]) -> None:
        color[n] = GRAY
        stack.append(n)
        for nxt in graph[n]:
            if color[nxt] == GRAY:
                cycle = stack[stack.index(nxt):] + [nxt]
                raise FormLogicCycleError(
                    "Zyklische set_value-Abhaengigkeit zwischen Feldern: " + " -> ".join(cycle)
                )
            if color[nxt] == WHITE:
                visit(nxt, stack)
        stack.pop()
        color[n] = BLACK

    for n in list(graph):
        if color[n] == WHITE:
            visit(n, [])


@dataclass
class FieldState:
    visible: bool = True
    required: bool = False
    readonly: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {"visible": self.visible, "required": self.required, "readonly": self.readonly}


@dataclass
class RuleApplicationResult:
    states: dict[str, FieldState] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)


def _apply_effect(states: dict[str, FieldState], path: str, effect: str, active: bool) -> None:
    st = states.setdefault(path, FieldState())
    if effect == "show":
        st.visible = active
    elif effect == "hide":
        st.visible = not active
    elif effect == "require":
        st.required = active
    elif effect == "readonly":
        st.readonly = active
    # set_value beeinflusst keine FieldState-Flags, nur `values` (siehe apply_rules).


def apply_rules(
    *,
    fields: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    values: dict[str, Any],
    view_id: str | None = None,
) -> RuleApplicationResult:
    """Wendet alle fuer `view_id` geltenden Regeln auf `values` an.

    - Regeln mit view_id=None gelten global (in jeder View inkl. view_id=None
      selbst); Regeln mit gesetzter view_id nur, wenn exakt diese View
      ausgewertet wird -- siehe form_logic_rules.view_id-Kommentar in
      Migration 0076.
    - Felder in einer Wiederholgruppe (form_groups) werden pro Zeile
      ausgewertet; der Zustands-Pfad ist dann "{group_key}[{index}].{key}"
      statt nur "{key}". Der Auswertungs-Kontext einer Zeile ist die Zeile
      selbst, ueberlagert ueber die Root-Werte (Root-Felder bleiben aus der
      Gruppe heraus referenzierbar).
    - Regeln koennen auch eine ganze Gruppe adressieren (target_key = ein
      FormGroup.key) -- deren Bedingung wird gegen die Root-Werte
      ausgewertet, der Zustands-Pfad ist dann einfach der Gruppen-key.
    - reihenfolge bestimmt die Anwendungsreihenfolge; bei mehreren Regeln
      auf demselben Ziel/Effekt gewinnt die zuletzt angewendete.
    """
    detect_cycles(rules)

    working_values: dict[str, Any] = {
        k: ([dict(row) for row in v] if isinstance(v, list) else v) for k, v in values.items()
    }
    field_group_of = {f["key"]: f.get("group_key") for f in fields}
    group_keys = {g["key"] for g in groups}

    applicable = sorted(
        (r for r in rules if r.get("view_id") in (None, view_id)),
        key=lambda r: r.get("reihenfolge", 0),
    )

    states: dict[str, FieldState] = {}

    for rule in applicable:
        target = rule["target_key"]
        effect = rule["effect"]

        if target in group_keys:
            active = evaluate_bool(rule["condition"], working_values)
            _apply_effect(states, target, effect, active)
            continue

        group_key = field_group_of.get(target)
        if group_key is None:
            active = evaluate_bool(rule["condition"], working_values)
            if effect == "set_value":
                if active:
                    # value ist ein Ausdruck (Literal ODER Formel mit
                    # var/Arithmetik) -- ein Literal wertet sich in
                    # evaluate_condition auf sich selbst aus, das ist also
                    # abwaertskompatibel zu reinen Fest-Werten.
                    working_values[target] = evaluate_condition(rule.get("value"), working_values)
            else:
                _apply_effect(states, target, effect, active)
            continue

        rows = working_values.setdefault(group_key, [])
        for idx, row in enumerate(rows):
            ctx = {**working_values, **row}
            active = evaluate_bool(rule["condition"], ctx)
            path = f"{group_key}[{idx}].{target}"
            if effect == "set_value":
                if active:
                    row[target] = evaluate_condition(rule.get("value"), ctx)
            else:
                _apply_effect(states, path, effect, active)

    return RuleApplicationResult(states=states, values=working_values)
