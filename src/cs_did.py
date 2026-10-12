"""
Callaway & Sant'Anna (2021) group-time average treatment effects.

Why not two-way fixed effects: with staggered adoption and effects that differ
across cohorts, TWFE implicitly uses already-treated units as controls for
later adopters and weights the resulting comparisons with weights that can be
negative. The estimate can then sit outside the range of every underlying
effect, sign included. CS avoids this by never comparing a treated unit to
another treated unit.

Implemented for the case this study needs - a never-treated comparison group
and no covariates - where the doubly-robust estimator collapses to a
difference in mean changes:

    ATT(g,t) = E[Y_t - Y_{g-1} | G = g] - E[Y_t - Y_{g-1} | never treated]

Inference is the multiplier bootstrap over unit-level influence functions,
which clusters at the unit by construction and gives simultaneous bands.
"""
from __future__ import annotations
import numpy as np

__all__ = ["CSResult", "att_gt", "aggregate_dynamic", "aggregate_overall",
           "pretrend_test"]


class CSResult:
    def __init__(self, cohorts, periods, att, inf, n_g):
        self.cohorts, self.periods = cohorts, periods
        self.att = att          # (n_cohorts, n_periods)
        self.inf = inf          # (n_units, n_cohorts, n_periods)
        self.n_g = n_g          # treated units per cohort


def att_gt(Y, G, never_value=10**8, min_cell=5, max_lead=12, max_lag=24):
    """Group-time ATTs.

    Y : (n_units, n_periods) float array, NaN where unobserved
    G : (n_units,) integer column index of first treatment; `never_value` for
        never-treated units.

    Only event times in [-max_lead-1, +max_lag] are computed. That bounds the
    influence-function array - which is (units x cohorts x periods) and would
    otherwise run to half a gigabyte per outcome - and it makes the overall
    estimand explicit: the average effect over the `max_lag` months following
    adoption, rather than an average over whatever window each cohort happens
    to have left before the panel ends.
    """
    Y = np.asarray(Y, float); G = np.asarray(G)
    n, T = Y.shape
    never = G >= never_value
    cohorts = np.array(sorted({int(g) for g in G[~never] if 1 <= g <= T - 1}))
    periods = np.arange(T)
    att = np.full((len(cohorts), T), np.nan)
    inf = np.zeros((n, len(cohorts), T), dtype=np.float32)
    n_g = np.zeros(len(cohorts), int)

    for gi, g in enumerate(cohorts):
        base = g - 1
        in_g = (G == g)
        n_g[gi] = int(in_g.sum())
        if n_g[gi] < min_cell:
            continue
        lo, hi = max(0, g - max_lead - 1), min(T - 1, g + max_lag)
        for t in range(lo, hi + 1):
            if t == base:
                continue
            dY = Y[:, t] - Y[:, base]
            ok = np.isfinite(dY)
            tr = ok & in_g
            ct = ok & never
            n1, n0 = int(tr.sum()), int(ct.sum())
            if n1 < min_cell or n0 < min_cell:
                continue
            m1, m0 = dY[tr].mean(), dY[ct].mean()
            att[gi, t] = m1 - m0
            # influence function: mean-zero within each group by construction
            inf[tr, gi, t] = ((dY[tr] - m1) / n1).astype(np.float32)
            inf[ct, gi, t] = (-(dY[ct] - m0) / n0).astype(np.float32)
    return CSResult(cohorts, periods, att, inf, n_g)


def _boot(theta_inf, n_boot, rng):
    """Multiplier bootstrap with Rademacher weights, clustered at the unit."""
    n = theta_inf.shape[0]
    draws = np.empty((n_boot, theta_inf.shape[1]))
    for b in range(n_boot):
        v = rng.choice(np.array([-1.0, 1.0]), size=n)
        draws[b] = v @ theta_inf
    return draws


def aggregate_dynamic(res, e_min=-12, e_max=12, n_boot=500, rng=None,
                      weight_by_size=True):
    """Event-study aggregation: average ATT(g, g+e) across cohorts."""
    rng = rng or np.random.default_rng(0)
    es = np.arange(e_min, e_max + 1)
    n = res.inf.shape[0]
    theta = np.full(len(es), np.nan)
    theta_inf = np.zeros((n, len(es)))
    for k, e in enumerate(es):
        num, wsum, ifs = 0.0, 0.0, np.zeros(n)
        for gi, g in enumerate(res.cohorts):
            t = g + e
            if t < 0 or t >= res.att.shape[1] or not np.isfinite(res.att[gi, t]):
                continue
            w = res.n_g[gi] if weight_by_size else 1.0
            num += w * res.att[gi, t]; wsum += w
            ifs += w * res.inf[:, gi, t]
        if wsum > 0:
            theta[k] = num / wsum
            theta_inf[:, k] = ifs / wsum
    draws = _boot(theta_inf, n_boot, rng)
    se = draws.std(axis=0, ddof=1)
    # simultaneous band: sup-t critical value
    with np.errstate(invalid="ignore", divide="ignore"):
        tstat = np.nanmax(np.abs(draws / np.where(se > 0, se, np.nan)), axis=1)
    crit = float(np.nanquantile(tstat, 0.95)) if np.isfinite(tstat).any() else np.nan
    return {"event_time": es, "att": theta, "se": se, "crit_simultaneous": crit}


def aggregate_overall(res, n_boot=500, rng=None):
    """One number: average post-treatment effect, cohort-size weighted."""
    rng = rng or np.random.default_rng(0)
    n = res.inf.shape[0]
    num, wsum, ifs = 0.0, 0.0, np.zeros(n)
    for gi, g in enumerate(res.cohorts):
        post = [t for t in range(g, res.att.shape[1]) if np.isfinite(res.att[gi, t])]
        if not post:
            continue
        a = float(np.mean([res.att[gi, t] for t in post]))
        i = res.inf[:, gi, post].mean(axis=1)
        w = res.n_g[gi]
        num += w * a; wsum += w; ifs += w * i
    if wsum == 0:
        return {"att": np.nan, "se": np.nan, "n_treated": 0, "n_cohorts": 0}
    theta = num / wsum
    draws = _boot((ifs / wsum)[:, None], n_boot, rng)
    return {"att": float(theta), "se": float(draws.std(ddof=1)),
            "n_treated": int(res.n_g.sum()),
            "n_cohorts": int(sum(1 for x in res.n_g if x >= 1))}


def pretrend_test(res, e_min=-12, n_boot=500, rng=None):
    """Joint test that every pre-treatment ATT(g,t) is zero.

    The naive statistic - sum of squared z-scores against a chi-square - is
    WRONG here, and badly so. Every pre-period ATT shares the same base period
    g-1, so one noisy draw at the base shifts them all together; the estimates
    are strongly positively correlated and the sum of squares has nothing like
    a chi-square null. On synthetic data with no pre-trend at all, that
    statistic returned 35.3 on 11 df.

    The correct statistic is the maximum absolute z across pre-periods,
    compared against a critical value taken from the multiplier bootstrap of
    the same influence functions - which carries the correlation with it.
    This is the sup-t band that Callaway and Sant'Anna report.
    """
    rng = rng or np.random.default_rng(0)
    dyn = aggregate_dynamic(res, e_min=e_min, e_max=-2, n_boot=n_boot, rng=rng)
    ok = np.isfinite(dyn["att"]) & np.isfinite(dyn["se"]) & (dyn["se"] > 0)
    if ok.sum() == 0:
        return {"max_abs_z": np.nan, "crit": np.nan, "reject": None, "k": 0}
    z = dyn["att"][ok] / dyn["se"][ok]
    crit = dyn["crit_simultaneous"]
    return {"max_abs_z": float(np.max(np.abs(z))),
            "crit": float(crit),
            "reject": bool(np.max(np.abs(z)) > crit) if np.isfinite(crit) else None,
            "k": int(ok.sum()),
            "naive_sum_z2": float(np.sum(z ** 2)),
            "event_time": dyn["event_time"][ok], "att": dyn["att"][ok],
            "se": dyn["se"][ok]}
