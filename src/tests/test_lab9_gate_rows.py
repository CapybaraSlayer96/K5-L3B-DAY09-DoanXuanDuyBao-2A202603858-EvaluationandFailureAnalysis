"""Gate checks the mean cannot see: per-row regression, ratchet under a renamed eval-set version."""
import copy

import pytest

pytestmark = pytest.mark.student

ROWS = [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": not (i == 0 and s == 2), "slices": []}
        for i in range(3) for s in (1, 2)]
SPEC = {"eval_set_version": "v2", "eval_set": "data/eval/eval_set_v2.jsonl",
        "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True, "threshold": {"min": 0.5}}],
        "row_regression": [{"metric": "pass_rate", "max_new_failures": 0, "blocking": True}]}


def test_failure_moved_to_another_seed_blocks():
    from lab9 import gate

    base = {"rows": copy.deepcopy(ROWS)}
    pr = {"rows": copy.deepcopy(ROWS)}
    pr["rows"][1]["pass_rate"], pr["rows"][0]["pass_rate"] = True, False   # E-000: @2 fixed, @1 broken
    assert gate.row_regression_check(pr, base, SPEC)[0] == ["rows:pass_rate"]
    assert gate.row_regression_check(base, base, SPEC)[0] == []


def test_renamed_version_does_not_skip_ratchet():
    from lab9 import gate

    rep = {"manifest": {"eval_set_sha": "x", "items": 3, "seeds": [1, 2]}, "rows": copy.deepcopy(ROWS),
           "metrics": {"pass_rate": 0.8333}, "evaluator_failures": []}
    loose = copy.deepcopy(SPEC)
    loose["eval_set_version"] = "v2b"
    loose["row_regression"][0]["max_new_failures"] = 5
    assert any("ratchet" in p for p in gate.integrity_check(rep, rep, loose, SPEC))
