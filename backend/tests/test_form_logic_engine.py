"""Testet app.services.form_logic_engine gegen die geteilten Fixtures unter
shared/form-logic-fixtures/ -- dieselben Fixtures laufen im Frontend gegen
formLogicEngine.ts (siehe frontend/src/utils/formLogicEngine.test.ts), damit
eine Regel nachweisbar in Backend und Frontend identisch entscheidet.
"""
import json
from pathlib import Path

import pytest

from app.services.form_logic_engine import (
    FieldState,
    FormLogicCycleError,
    apply_rules,
    detect_cycles,
    evaluate_bool,
)

_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "shared" / "form-logic-fixtures"


def _load(name: str) -> list[dict]:
    return json.loads((_FIXTURES_DIR / name).read_text())


@pytest.mark.parametrize("case", _load("condition-eval.json"), ids=lambda c: c["name"])
def test_condition_eval_fixtures(case):
    assert evaluate_bool(case["condition"], case["context"]) == case["expected"]


@pytest.mark.parametrize("case", _load("cycle-detection.json"), ids=lambda c: c["name"])
def test_cycle_detection_fixtures(case):
    if case["expect_cycle"]:
        with pytest.raises(FormLogicCycleError):
            detect_cycles(case["rules"])
    else:
        detect_cycles(case["rules"])  # darf nicht werfen


def _states_as_dicts(states: dict[str, FieldState]) -> dict[str, dict]:
    return {path: state.as_dict() for path, state in states.items()}


@pytest.mark.parametrize("case", _load("rule-application.json"), ids=lambda c: c["name"])
def test_rule_application_fixtures(case):
    result = apply_rules(
        fields=case["fields"],
        groups=case["groups"],
        rules=case["rules"],
        values=case["values"],
        view_id=case["view_id"],
    )
    assert _states_as_dicts(result.states) == case["expected_states"]
    assert result.values == case["expected_values"]
