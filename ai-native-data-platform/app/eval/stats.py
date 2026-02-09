from __future__ import annotations

import random
from typing import Callable, Dict, List, Tuple


def bootstrap_diff(a: List[float], b: List[float], iters: int = 2000, seed: int = 7) -> Dict[str, float]:
    """Bootstrap estimate of mean difference (b - a) with CI and two-sided p-value."""
    if not a or not b:
        return {"diff": 0.0, "p_value": 1.0, "ci_low": 0.0, "ci_high": 0.0}

    rng = random.Random(seed)
    diffs: List[float] = []
    n_a = len(a)
    n_b = len(b)

    mean_a = sum(a) / n_a
    mean_b = sum(b) / n_b
    obs = mean_b - mean_a

    for _ in range(iters):
        sa = [a[rng.randrange(n_a)] for _ in range(n_a)]
        sb = [b[rng.randrange(n_b)] for _ in range(n_b)]
        diffs.append((sum(sb) / n_b) - (sum(sa) / n_a))

    diffs.sort()
    ci_low = diffs[int(0.025 * (iters - 1))]
    ci_high = diffs[int(0.975 * (iters - 1))]

    # Two-sided p-value via bootstrap: proportion of diffs with opposite sign and >= magnitude.
    opp = sum(1 for d in diffs if abs(d) >= abs(obs) and (d * obs) <= 0)
    p = max(1.0 / iters, opp / iters)

    return {"diff": float(obs), "p_value": float(p), "ci_low": float(ci_low), "ci_high": float(ci_high)}
