# =====================================================================
# NB8 Arm B (v2) — non-gating placebo with NOT-YET-TREATED controls
#
#     %run /content/drive/MyDrive/peltzman/nb8_armb2.py
#
# Why not never-treated: every repository in the frame adopts an Actions workflow
# inside the window (Actions reached general availability in Nov 2019, four months
# after the window opens), so a never-automated control group does not exist.
# Callaway and Sant'Anna's other comparison group, not-yet-treated, is used instead:
# for cohort g at period t, controls are repositories whose own first workflow
# arrives after max(t, g).
#
# Reuses state/nb8_nongating_first.parquet written by nb8_armb.py, so no re-scan.
# =====================================================================
import os, json
import numpy as np, pandas as pd

PARQ = os.path.join(STATE, "nb8_nongating_first.parquet")
assert os.path.exists(PARQ), "run nb8_armb.py first to build the first-workflow table"

T0, TMAX = int(panel[COL_MONTH].min()), int(panel[COL_MONTH].max())
def ym_to_t(y, m): return int(y) * 12 + (int(m) - 1)

first = pd.read_parquet(PARQ)
reps  = pd.read_csv(os.path.join("/content/drive/MyDrive/peltzman/raw",
                                 "repositories.csv.gz"),
                    usecols=["name", "created"])
reps["created"] = pd.to_datetime(reps["created"], errors="coerce", utc=True)
reps["t_created"] = [ym_to_t(d.year, d.month) if pd.notna(d) else np.nan
                     for d in reps["created"]]
first = first.merge(reps[["name","t_created"]], left_on="repo", right_on="name", how="left")

elig = first["t_first"].between(T0, TMAX) & ((first["t_first"] - first["t_created"]) >= 12)
gmap = dict(zip(first.loc[elig,"repo"], first.loc[elig,"t_first"].astype(int)))
print(f"eligible non-gating adopters: {len(gmap):,} | cohorts {len(set(gmap.values()))}")


def att_cells_nyt(Y, G, min_cell=MIN_CELL, max_lead=MAX_LEAD, max_lag=MAX_LAG,
                  drop_event0=False):
    """Callaway-Sant'Anna with NOT-YET-TREATED controls.

    For cohort g and period t the control group is every unit whose own adoption
    falls strictly after max(t, g), so no unit is used as a control in a period
    where it is already treated.
    """
    N, cols = len(Y.index), list(Y.columns)
    cpos, cset = {c: j for j, c in enumerate(cols)}, set(cols)
    Yv, Gv = Y.values, G.values
    out = {}
    for g in sorted(set(int(x) for x in Gv)):
        if (g - 1) not in cset: continue
        base, ing = Yv[:, cpos[g - 1]], (Gv == g)
        if ing.sum() < min_cell: continue
        for t in cols:
            e = t - g
            if e < -max_lead or e > max_lag or e == -1: continue
            if drop_event0 and e == 0: continue
            d  = Yv[:, cpos[t]] - base
            ok = np.isfinite(d)
            ctl = (Gv > max(t, g)) & ok          # not yet treated at t
            m1  = ing & ok
            n1, n0 = int(m1.sum()), int(ctl.sum())
            if n1 < min_cell or n0 < min_cell: continue
            a1, a0 = d[m1].mean(), d[ctl].mean()
            psi = np.zeros(N)
            psi[m1]  =  (d[m1]  - a1) * (N / n1)
            psi[ctl] = -(d[ctl] - a0) * (N / n0)
            out[(g, t)] = (float(a1 - a0), psi, n1)
    return out


rows = []
for outcome in OUTCOMES:
    Y, _ = build_wide(panel, outcome)
    idx  = Y.index
    G    = pd.Series([gmap.get(r, NEVER_VALUE) for r in idx], index=idx, dtype="int64")
    keep = (G.values != NEVER_VALUE)
    Yk, Gk = Y[keep], G[keep]
    c = att_cells_nyt(Yk, Gk)
    if not c:
        rows.append({"outcome": outcome, "label": OUTCOMES[outcome], "att": np.nan,
                     "se": np.nan, "t": np.nan, "n_cells": 0, "n": int(keep.sum())})
        print(f"  {OUTCOMES[outcome]:<24} no usable cells"); continue
    att, se, ncell = overall_att(c)
    rows.append({"outcome": outcome, "label": OUTCOMES[outcome], "att": att, "se": se,
                 "t": att/se if se else np.nan, "n_cells": ncell, "n": int(keep.sum())})
    print(f"  {OUTCOMES[outcome]:<24} att {att:+.5f}  se {se:.5f}  "
          f"t {att/se if se else float('nan'):+.2f}  cells {ncell}", flush=True)

R1b = pd.DataFrame(rows)
R1b["significant"] = R1b["t"].abs() > 1.96
print("\n" + R1b[["label","att","se","t","n_cells","n","significant"]].to_string(index=False))
sig = R1b.loc[R1b["significant"] == True, "label"].tolist()
print(f"\nnull on {int((R1b['significant'] == False).sum())} of {len(R1b)} outcomes")
print("significant:", sig or "none")

# the comparison that matters: same estimator, same controls style, real treatment
print("\n--- for reference, Treatment A under never-treated controls ---")
for o in ("o5_self_merge_rate", "o1_reviewers_per_pr"):
    Y, G = build_wide(panel, o)
    a, s, _ = overall_att(att_cells(Y, G, never_value=NEVER_VALUE))
    print(f"  {OUTCOMES[o]:<24} att {a:+.5f}  se {s:.5f}  t {a/s:+.2f}")

R1b.to_csv(os.path.join(RESULTS, "nb8_r1b_placebo_nyt.csv"), index=False)
json.dump({"design": "not-yet-treated controls", "n_adopters": len(gmap),
           "cohorts": len(set(gmap.values())), "significant": sig,
           "rows": R1b.to_dict("records")},
          open(os.path.join(STATE, "nb8_r1b_nyt_summary.json"), "w"), indent=2, default=float)
print("\nwrote", os.path.join(RESULTS, "nb8_r1b_placebo_nyt.csv"))
