"""
Peltzman Protocol - panel construction, fast two-way fixed-effects DiD, and
randomisation-based power.

The estimator here is deliberately simple: it exists to check pre-trends and to
measure how much noise the design has, not to produce the paper's numbers.
Callaway-Sant'Anna in NB5 does that. But a fast TWFE fit is what makes a
permutation study affordable, and a permutation study is a far more honest
account of power than plugging a guessed standard deviation into a formula.
"""
from __future__ import annotations
import numpy as np

__all__ = ["month_index", "demean_two_way", "twfe_did", "event_study",
           "placebo_se", "mde_from_se"]


def month_index(ym):
    """'YYYY-MM' -> integer month, so arithmetic and sorting are trivial."""
    y, m = str(ym).split("-")
    return int(y) * 12 + int(m) - 1


def demean_two_way(y, unit, time, iters=30, tol=1e-10):
    """Absorb unit and time fixed effects by alternating projections.

    Equivalent to residualising on the full dummy set, but O(n) per sweep
    instead of building a matrix with tens of thousands of columns. Converges
    geometrically; 30 sweeps is far past what a panel this shape needs.
    """
    y = np.asarray(y, dtype=np.float64).copy()
    nu, nt = unit.max() + 1, time.max() + 1
    cu, ct = np.bincount(unit, minlength=nu), np.bincount(time, minlength=nt)
    cu[cu == 0] = 1; ct[ct == 0] = 1
    for _ in range(iters):
        prev = y[:1000].copy() if y.size >= 1000 else y.copy()
        y -= (np.bincount(unit, y, minlength=nu) / cu)[unit]
        y -= (np.bincount(time, y, minlength=nt) / ct)[time]
        cur = y[:1000] if y.size >= 1000 else y
        if np.max(np.abs(cur - prev)) < tol:
            break
    return y


def twfe_did(y, treat, unit, time, cluster=None):
    """Two-way fixed-effects DiD. Returns (beta, se, n).

    `treat` is the post-treatment indicator. Standard errors are clustered on
    `cluster` (default: unit), because repo-months within a repo are anything
    but independent and unclustered errors here would be fiction.
    """
    y = np.asarray(y, float); d = np.asarray(treat, float)
    keep = np.isfinite(y) & np.isfinite(d)
    y, d, unit, time = y[keep], d[keep], unit[keep], time[keep]
    if y.size < 10 or d.sum() < 2 or (1 - d).sum() < 2:
        return np.nan, np.nan, int(y.size)
    yt = demean_two_way(y, unit, time)
    dt = demean_two_way(d, unit, time)
    denom = float(dt @ dt)
    if denom <= 0:
        return np.nan, np.nan, int(y.size)
    beta = float(dt @ yt) / denom
    resid = yt - beta * dt
    g = unit if cluster is None else np.asarray(cluster)[keep]
    order = np.argsort(g, kind="stable")
    gs, sc, rs = g[order], dt[order], resid[order]
    bounds = np.flatnonzero(np.r_[True, gs[1:] != gs[:-1], True])
    meat = 0.0
    for a, b in zip(bounds[:-1], bounds[1:]):
        meat += float(sc[a:b] @ rs[a:b]) ** 2
    ng = len(bounds) - 1
    if ng < 2:
        return beta, np.nan, int(y.size)
    adj = ng / (ng - 1.0)
    return beta, float(np.sqrt(adj * meat) / denom), int(y.size)


def event_study(y, evt, unit, time, leads=12, lags=12, ref=-1):
    """Coefficients by event time. `evt` is months since treatment; use a large
    sentinel (e.g. 9999) for never-treated units so they act as controls.

    Returns {event_time: (beta, se)} with `ref` omitted as the base period.
    """
    y = np.asarray(y, float); evt = np.asarray(evt)
    out = {}
    for k in range(-leads, lags + 1):
        if k == ref:
            continue
        d = (evt == k).astype(float)
        # compare period k against the reference period and the never-treated
        mask = np.isfinite(y) & ((evt == k) | (evt == ref) | (evt > 9000))
        if d[mask].sum() < 5:
            out[k] = (np.nan, np.nan); continue
        b, se, _ = twfe_did(y[mask], d[mask], unit[mask], time[mask])
        out[k] = (b, se)
    return out


def placebo_se(y, unit, time, n_treated, cohort_months, rng, n_perm=200,
               min_post=6):
    """Randomisation inference on never-treated units.

    Assign `n_treated` units a fake adoption month drawn from the real cohort
    distribution, estimate the DiD, repeat. The spread of the resulting
    estimates IS the standard error of this design at this sample size - no
    distributional assumption, no guessed sigma. The centre doubles as a
    placebo test: it should sit on zero.
    """
    y = np.asarray(y, float)
    units = np.unique(unit)
    if len(units) <= n_treated or len(cohort_months) == 0:
        return np.nan, np.nan, 0
    tmax = time.max()
    est = []
    for _ in range(n_perm):
        chosen = rng.choice(units, size=n_treated, replace=False)
        gmap = {u: rng.choice(cohort_months) for u in chosen}
        d = np.zeros(y.size)
        sel = np.isin(unit, chosen)
        gs = np.array([gmap.get(u, 10**9) for u in unit[sel]])
        d[sel] = (time[sel] >= gs).astype(float)
        if d.sum() < min_post:
            continue
        b, _, _ = twfe_did(y, d, unit, time)
        if np.isfinite(b):
            est.append(b)
    if len(est) < 20:
        return np.nan, np.nan, len(est)
    est = np.array(est)
    return float(est.mean()), float(est.std(ddof=1)), len(est)


def mde_from_se(se, alpha=0.05, power=0.80):
    """Smallest effect detectable at the given power. 1.96 + 0.84 for the
    conventional 5% / 80%."""
    return np.nan if not np.isfinite(se) else float(2.802 * se)
