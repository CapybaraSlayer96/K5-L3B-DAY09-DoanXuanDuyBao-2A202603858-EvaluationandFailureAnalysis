"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError("human and judge differ in length")
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for h, j in zip(human, judge):
        h_pos, j_pos = h.strip().upper() == POS, j.strip().upper() == POS
        cm[("t" if h_pos == j_pos else "f") + ("p" if j_pos else "n")] += 1
    return cm


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    p = cm["tp"] / (cm["tp"] + cm["fp"]) if cm["tp"] + cm["fp"] else 0.0
    r = cm["tp"] / (cm["tp"] + cm["fn"]) if cm["tp"] + cm["fn"] else 0.0
    return p, r


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    cm = confusion(human, judge)
    n = sum(cm.values())
    if n == 0:
        raise ValueError("kappa undefined on empty input")
    p_o = (cm["tp"] + cm["tn"]) / n
    h_pos, j_pos = (cm["tp"] + cm["fn"]) / n, (cm["tp"] + cm["fp"]) / n
    p_e = h_pos * j_pos + (1 - h_pos) * (1 - j_pos)
    if p_e >= 1.0:
        raise ValueError("kappa undefined: chance agreement is 1")
    return (p_o - p_e) / (1 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1].
    NaN when sens + spec <= 1: a judge no better than chance cannot correct anything."""
    denom = sensitivity + specificity - 1
    if denom <= 0:
        return float("nan")
    return min(1.0, max(0.0, (observed_rate + specificity - 1) / denom))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy.stats import bootstrap

    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if x.shape != y.shape:
        raise ValueError("paired bootstrap needs the same items in the same order")
    d = float(x.mean() - y.mean()) if len(x) else 0.0
    if np.array_equal(x, y):
        return (0.0, 0.0, 0.0)
    if np.all(x - y == x[0] - y[0]):        # constant difference: zero variance, CI collapses
        return (d, d, d)
    res = bootstrap((x, y), lambda u, v, axis=-1: u.mean(axis=axis) - v.mean(axis=axis),
                    paired=True, vectorized=True, n_resamples=n_resamples, confidence_level=confidence,
                    method="percentile", rng=np.random.default_rng(rng))
    return (d, float(res.confidence_interval.low), float(res.confidence_interval.high))


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    from math import comb

    n, c, k = _check_nck(n, c, k)
    return 1.0 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    from math import comb

    n, c, k = _check_nck(n, c, k)
    return comb(c, k) / comb(n, k)


def _check_nck(n: int, c: int, k: int) -> tuple[int, int, int]:
    """Coerce to int; raise ValueError on non-integers or unless 0 <= c <= n and 1 <= k <= n."""
    import operator

    if any(isinstance(v, bool) for v in (n, c, k)):
        raise ValueError(f"n, c, k must be integers, not bool: {(n, c, k)!r}")
    try:
        n, c, k = (operator.index(v) for v in (n, c, k))
    except TypeError as e:
        raise ValueError(f"n, c, k must be integers, got {(n, c, k)!r}") from e
    if n < 1 or not 0 <= c <= n or not 1 <= k <= n:
        raise ValueError(f"invalid (n={n}, c={c}, k={k}): need n >= 1, 0 <= c <= n, 1 <= k <= n")
    return n, c, k
