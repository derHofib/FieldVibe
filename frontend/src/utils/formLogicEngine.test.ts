// Testet formLogicEngine.ts gegen die geteilten Fixtures unter
// shared/form-logic-fixtures/ -- dieselben Fixtures laufen im Backend gegen
// app/services/form_logic_engine.py (siehe
// backend/tests/test_form_logic_engine.py), damit eine Regel nachweisbar in
// Backend und Frontend identisch entscheidet. Die Fixtures werden bewusst
// per fs.readFileSync statt per ES-Import geladen -- ein Import wuerde ueber
// Vite's Modulaufloesung laufen (server.fs.allow ist auf den frontend/-
// Workspace-Root beschraenkt), reines Node-Dateilesen umgeht das.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  applyRules,
  detectCycles,
  evaluateBool,
  evaluateCondition,
  FormLogicCycleError,
  type FieldDef,
  type GroupDef,
  type LogicRule,
} from "./formLogicEngine";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = path.resolve(__dirname, "../../../shared/form-logic-fixtures");

function load<T>(name: string): T[] {
  return JSON.parse(readFileSync(path.join(FIXTURES_DIR, name), "utf-8"));
}

interface ConditionEvalCase {
  name: string;
  condition: unknown;
  context: Record<string, unknown>;
  expected: boolean;
}

interface ArithmeticEvalCase {
  name: string;
  expression: unknown;
  context: Record<string, unknown>;
  expected: number | null;
}

interface CycleDetectionCase {
  name: string;
  rules: LogicRule[];
  expect_cycle: boolean;
}

interface RuleApplicationCase {
  name: string;
  fields: FieldDef[];
  groups: GroupDef[];
  rules: LogicRule[];
  values: Record<string, unknown>;
  view_id: string | null;
  expected_states: Record<string, { visible: boolean; required: boolean; readonly: boolean }>;
  expected_values: Record<string, unknown>;
}

describe("evaluateCondition (condition-eval.json)", () => {
  for (const c of load<ConditionEvalCase>("condition-eval.json")) {
    it(c.name, () => {
      expect(evaluateBool(c.condition, c.context)).toBe(c.expected);
    });
  }
});

describe("evaluateCondition arithmetik (arithmetic-eval.json)", () => {
  for (const c of load<ArithmeticEvalCase>("arithmetic-eval.json")) {
    it(c.name, () => {
      expect(evaluateCondition(c.expression, c.context)).toBe(c.expected);
    });
  }
});

describe("detectCycles (cycle-detection.json)", () => {
  for (const c of load<CycleDetectionCase>("cycle-detection.json")) {
    it(c.name, () => {
      if (c.expect_cycle) {
        expect(() => detectCycles(c.rules)).toThrow(FormLogicCycleError);
      } else {
        expect(() => detectCycles(c.rules)).not.toThrow();
      }
    });
  }
});

describe("applyRules (rule-application.json)", () => {
  for (const c of load<RuleApplicationCase>("rule-application.json")) {
    it(c.name, () => {
      const result = applyRules({
        fields: c.fields,
        groups: c.groups,
        rules: c.rules,
        values: c.values,
        viewId: c.view_id,
      });
      const statesAsObject = Object.fromEntries(result.states.entries());
      expect(statesAsObject).toEqual(c.expected_states);
      expect(result.values).toEqual(c.expected_values);
    });
  }
});
