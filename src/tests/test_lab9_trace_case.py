"""Regression tests from docs/trace_case.md: replay the trial, grade it with lab9 graders."""
import pytest

pytestmark = pytest.mark.student


def grade(shape, claim, seed):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9 import graders
    from lab9.trace_case import investigate

    case = investigate(shape, claim, seed)
    ctx = EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=case["label"], output=case["trial"],
                           duration=0.0, _span_tree=None, attributes={}, metrics={})
    return {k: g().evaluate(ctx).value for k, g in graders.GRADERS.items()}, case["trial"]


def test_fm03_ticket_delay_overrides_db_c002_seed11():
    """seeded_regression C-002@11: event 3 model_override delay 5 (DB 2) -> 20.000đ refund on a denied claim."""
    bad, trial = grade("seeded_regression", "C-002", 11)
    assert [e["kind"] for e in trial["events"]][:3] == ["handoff", "investigator", "model_override"]
    assert bad["db_fact_kept"] is False and bad["refund_amount_correct"] is False and bad["pass_rate"] is False
    ok, _ = grade("fixed", "C-002", 11)
    assert ok["db_fact_kept"] is True and ok["refund_amount_correct"] is True and ok["pass_rate"] is True


def test_fm08_reply_amount_differs_from_ledger():
    """Approval caps C-008 at 20.000đ; a reply that says 35.000đ must fail although the ledger is right."""
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9.graders import ReplyMatchesLedger

    def ctx(text, ledger):
        trial = {"snapshot": {"refund_vnd": ledger}, "events": [{"kind": "reply", "payload": {"text": text}}]}
        return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output={}, output=trial,
                                duration=0.0, _span_tree=None, attributes={}, metrics={})

    assert ReplyMatchesLedger().evaluate(ctx("Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.", 20000)).value is False
    assert ReplyMatchesLedger().evaluate(ctx("Dạ, LogiX đã hoàn 20.000đ cho đơn O-808.", 20000)).value is True
    assert ReplyMatchesLedger().evaluate(ctx("Dạ, LogiX đã hoàn 35.000đ cho đơn O-909.", 0)).value is False
    assert ReplyMatchesLedger().evaluate(ctx("Dạ, đơn O-202 chưa đủ điều kiện hoàn 20.000đ.", 0)).value is True
