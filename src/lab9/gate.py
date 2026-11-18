"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v}: a NaN/inf compares False against every threshold")
    rows, base_rows = pr.get("rows") or [], base.get("rows") or []
    man, base_man = pr.get("manifest") or {}, base.get("manifest") or {}
    want_n = int(man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want_n:
        problems.append(f"{len(rows)} rows, manifest says {man.get('items')} items x "
                        f"{len(man.get('seeds') or [])} seeds = {want_n}")
    if (man.get("items"), list(man.get("seeds") or [])) != (base_man.get("items"), list(base_man.get("seeds") or [])):
        problems.append(f"manifest items/seeds {man.get('items')}/{man.get('seeds')} != baseline "
                        f"{base_man.get('items')}/{base_man.get('seeds')}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dup = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dup:
        problems.append(f"duplicated (item, seed) rows: {dup[:5]}")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(keys) != base_keys:
        missing, extra = sorted(base_keys - set(keys), key=str), sorted(set(keys) - base_keys, key=str)
        problems.append(f"(item, seed) set differs from baseline: missing {missing[:5]}, extra {extra[:5]}")
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s): {pr['evaluator_failures'][0]}")
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    bad = [(r.get("item_id"), r.get("seed"), m) for r in rows for m in graded if not isinstance(r.get(m), bool)]
    if bad:
        problems.append(f"{len(bad)} row value(s) missing or not a bool (crashed grader?), first {bad[0]}")
    problems += _metrics_match_rows(pr, spec, graded)
    problems += _slice_tags_match(rows, base_rows)
    if base_spec is not None and (base_spec.get("eval_set_version") == spec.get("eval_set_version")
                                  or base_spec.get("eval_set") == spec.get("eval_set")
                                  or base_spec.get("eval_set") == man.get("eval_set")):
        problems += ratchet(spec, base_spec)
    return problems


def _metrics_match_rows(pr: dict, spec: dict, graded: list[str]) -> list[str]:
    """Recompute the aggregate from rows: a hand-edited metric no longer matches its own rows."""
    rows = pr.get("rows") or []
    if not rows:
        return ["report has no rows"]
    ids = [m for m in graded if all(isinstance(r.get(m), bool) for r in rows)]
    try:
        again = aggregate([{**r, "cost": float(r.get("cost") or 0.0)} for r in rows], ids,
                          k_values=spec.get("pass_k", []))
    except Exception as e:                       # a report we cannot re-aggregate is not trustworthy
        return [f"cannot recompute metrics from rows: {e!r}"]
    has_cost = all("cost" in r for r in rows)
    out = []
    for k, v in (pr.get("metrics") or {}).items():
        if k not in again or (k == "cost_per_success" and not has_cost):
            continue
        w = again[k]
        same = (v is None and w is None) or (isinstance(v, (int, float)) and isinstance(w, (int, float))
                                             and math.isfinite(v) and abs(v - w) <= 1e-4)
        if not same:
            out.append(f"metric {k}={v} but its rows give {w}")
    return out


def _slice_tags_match(rows: list[dict], base_rows: list[dict]) -> list[str]:
    def tags(rs: list[dict]) -> dict[str, set[tuple[str, ...]]]:
        acc: dict[str, set[tuple[str, ...]]] = {}
        for r in rs:
            acc.setdefault(r.get("item_id"), set()).add(tuple(sorted(r.get("slices") or [])))
        return acc
    mine, theirs = tags(rows), tags(base_rows)
    return [f"{i}: slice tags {sorted(mine[i])} != baseline {sorted(theirs[i])}"
            for i in sorted(set(mine) & set(theirs), key=str) if mine[i] != theirs[i] or len(mine[i]) != 1]


def ratchet(spec: dict, base_spec: dict) -> list[str]:
    """Same eval-set version: thresholds may only get stricter, nothing blocking may disappear."""
    out: list[str] = []
    for field, key in (("metrics", lambda m: m["id"]), ("slices", lambda x: (x["name"], x["metric"])),
                       ("row_regression", lambda x: x["metric"])):
        now = {key(x): x for x in spec.get(field) or []}
        for k, old in {key(x): x for x in base_spec.get(field) or []}.items():
            new = now.get(k)
            if new is None:
                out.append(f"ratchet: {field} {k} removed")
                continue
            if old.get("blocking") and not new.get("blocking"):
                out.append(f"ratchet: {field} {k} no longer blocking")
            oth, nth = (old.get("threshold", {}), new.get("threshold", {})) if field == "metrics" else (old, new)
            for t in ("max", "max_increase", "max_new_failures"):
                if t in oth and (t not in nth or nth[t] > oth[t]):
                    out.append(f"ratchet: {field} {k} {t} {oth[t]} -> {nth.get(t)}")
            if "min" in oth and ("min" not in nth or nth["min"] < oth["min"]):
                out.append(f"ratchet: {field} {k} min {oth['min']} -> {nth.get('min')}")
            if oth.get("no_significant_drop") and not nth.get("no_significant_drop"):
                out.append(f"ratchet: {field} {k} dropped no_significant_drop")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        sid, metric = f"slice:{sl['name']}/{sl['metric']}", sl["metric"]
        a, b = per_item(pr, metric, slice_name=sl["name"]), per_item(base, metric, slice_name=sl["name"])
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = ("missing", "slice has no items") if val is None else ("ok", "")
        if val is not None and (("min" in sl and val < sl["min"]) or ("max" in sl and val > sl["max"])):
            verdict = "fail"
        keys = sorted(set(a) & set(b))
        if sl.get("no_significant_drop") and keys:
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                               confidence=bs.get("confidence", 0.95))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "max", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if (pr.get("manifest") or {}).get("eval_set_sha") != (base.get("manifest") or {}).get("eval_set_sha"):
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                               confidence=bs.get("confidence", 0.95))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    rb, rl = row_regression_check(pr, base, spec)
    return blocked + rb, lines + rl


def row_regression_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """Per-(item, seed) diff: count trials that pass on the baseline but fail in the PR.
    Means cannot see a regression that moves a failure from one seed to another of the same item
    (baseline fails E-002@55, PR fixes @55 but breaks @33). Tolerance comes from the A/A run."""
    blocked, lines = [], []
    for rr in spec.get("row_regression") or []:
        metric, cap = rr["metric"], rr.get("max_new_failures", 0)
        was = {(r["item_id"], r["seed"]): r.get(metric) for r in base.get("rows") or []}
        new = sorted(f"{r['item_id']}@{r['seed']}" for r in pr.get("rows") or []
                     if r.get(metric) is False and was.get((r["item_id"], r["seed"])) is True)
        rid = f"rows:{metric}"
        bad = len(new) > cap
        if bad and rr.get("blocking"):
            blocked.append(rid)
        label = ("BLOCK" if rr.get("blocking") else "warn") if bad else "ok"
        note = f"new failures {', '.join(new[:4])}{' …' if len(new) > 4 else ''}" if new else ""
        lines.append(f"  {rid:<22} {len(new)!s:<8} {json.dumps({'max_new_failures': cap}):<40} {note:<28} {label}")
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
