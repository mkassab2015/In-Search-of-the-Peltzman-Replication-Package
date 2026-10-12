# =====================================================================
# NB8 Arm B (v4) — MARGINAL non-gating placebo, matched to Treatment B
#
#     %run /content/drive/MyDrive/peltzman/nb8_armb4.py
#
# Problem with v2/v3: its treatment was "first workflow ever", a far larger event
# than "add a gate to existing CI", and its not-yet-treated controls were
# repositories with no workflows at all, a group that thins and self-selects as the
# horizon lengthens. Both inflate the placebo.
#
# This version matches Treatment B exactly:
#   population : repositories that already have a workflow and never gate
#   treatment  : the month they add ANOTHER workflow file, >= 3 months after the first
#   controls   : same population, not yet treated at t
#   eligibility: >= 12 months of repository history, adoption inside the window
#
# Treatment B reference (self-merge): coverage gate +0.0451, linter +0.0295,
# test suite +0.0388, type checker +0.0309, merge queue +0.0234.
# =====================================================================
import os, json, time
import numpy as np, pandas as pd

RAW   = "/content/drive/MyDrive/peltzman/raw"
CACHE = os.path.join(STATE, "nb8_marginal_nongating.parquet")
GAP   = 3     # months, same robustness threshold as Treatment B
for _n in ("panel","COL_MONTH","COL_REPO","OUTCOMES","NEVER_VALUE","STATE","RESULTS",
           "build_wide","overall_att","MIN_CELL","MAX_LEAD","MAX_LAG"):
    assert _n in dir(), f"{_n} not defined - run NB8 cells 1 to 6 first"
T0, TMAX = int(panel[COL_MONTH].min()), int(panel[COL_MONTH].max())
def ym_to_t(y, m): return int(y) * 12 + (int(m) - 1)


# --- not-yet-treated estimator (self-contained; same as nb8_armb2.py) ---------
if "att_cells_nyt" not in dir():
    def att_cells_nyt(Y, G, min_cell=MIN_CELL, max_lead=MAX_LEAD, max_lag=MAX_LAG,
                      drop_event0=False):
        """Callaway-Sant'Anna with NOT-YET-TREATED controls: for cohort g at period t,
        controls are units whose own adoption falls strictly after max(t, g)."""
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
                ctl = (Gv > max(t, g)) & ok
                m1  = ing & ok
                n1, n0 = int(m1.sum()), int(ctl.sum())
                if n1 < min_cell or n0 < min_cell: continue
                a1, a0 = d[m1].mean(), d[ctl].mean()
                psi = np.zeros(N)
                psi[m1]  =  (d[m1]  - a1) * (N / n1)
                psi[ctl] = -(d[ctl] - a0) * (N / n0)
                out[(g, t)] = (float(a1 - a0), psi, n1)
        return out
    print("defined att_cells_nyt")

controls = set(json.load(open(os.path.join(STATE, "nb1_controls.json"))))

if os.path.exists(CACHE):
    marg = pd.read_parquet(CACHE)
    print(f"reusing {CACHE} ({len(marg):,} repos)")
else:
    t0, parts, nrows = time.time(), [], 0
    reader = pd.read_csv(os.path.join(RAW, "workflows.csv.gz"),
                         usecols=["repository","file_path","committed_date","valid_workflow"],
                         chunksize=1_000_000, low_memory=False)
    for i, ch in enumerate(reader):
        nrows += len(ch)
        ch = ch[ch["repository"].isin(controls)]
        if len(ch):
            ch = ch[ch["valid_workflow"].astype(str).str.lower().str.startswith("t")]
        if len(ch):
            ch = ch.assign(_d=pd.to_numeric(ch["committed_date"], errors="coerce")).dropna(subset=["_d"])
            parts.append(ch.groupby(["repository","file_path"], as_index=False)["_d"].min())
        print(f"  chunk {i:>3}  rows {nrows:>10,}  {time.time()-t0:6.0f}s", flush=True)
    fv = pd.concat(parts, ignore_index=True)
    fv = fv.groupby(["repository","file_path"], as_index=False)["_d"].min()
    ts = pd.to_datetime(fv["_d"], unit="s", utc=True)
    fv["t"] = [ym_to_t(d.year, d.month) for d in ts]
    fv = fv.sort_values(["repository","t"])

    rows = []
    for repo, grp in fv.groupby("repository", sort=False):
        ts_ = grp["t"].values
        t_first = int(ts_[0])
        later = ts_[ts_ >= t_first + GAP]
        rows.append({"repo": repo, "t_first": t_first,
                     "t_marginal": int(later[0]) if len(later) else np.nan,
                     "n_files": len(grp)})
    marg = pd.DataFrame(rows)
    marg.to_parquet(CACHE, index=False)
    print(f"wrote {CACHE} ({len(marg):,} repos, {time.time()-t0:.0f}s)")

reps = pd.read_csv(os.path.join(RAW, "repositories.csv.gz"), usecols=["name","created"])
reps["created"] = pd.to_datetime(reps["created"], errors="coerce", utc=True)
reps["t_created"] = [ym_to_t(d.year, d.month) if pd.notna(d) else np.nan for d in reps["created"]]
marg = marg.merge(reps[["name","t_created"]], left_on="repo", right_on="name", how="left")

has   = marg["t_marginal"].notna()
elig  = has & marg["t_marginal"].between(T0, TMAX) & \
        ((marg["t_marginal"] - marg["t_created"]) >= 12)
gmap  = dict(zip(marg.loc[elig,"repo"], marg.loc[elig,"t_marginal"].astype(int)))
pop   = set(marg.loc[marg["t_first"] <= TMAX, "repo"])     # already-automated population
print(f"\nalready-automated never-gating repos : {len(pop):,}")
print(f"with a marginal workflow (gap>={GAP}m)   : {int(has.sum()):,}")
print(f"eligible marginal adopters            : {len(gmap):,} | cohorts {len(set(gmap.values()))}")

rows = []
for outcome in OUTCOMES:
    Y, _ = build_wide(panel, outcome)
    idx  = Y.index
    G    = pd.Series([gmap.get(r, NEVER_VALUE) for r in idx], index=idx, dtype="int64")
    keep = np.array([(r in pop) for r in idx])             # restrict to the matched population
    Yk, Gk = Y[keep], G[keep]
    n_tr = int((Gk.values != NEVER_VALUE).sum())
    c = att_cells_nyt(Yk, Gk)
    if not c:
        rows.append({"outcome": outcome, "label": OUTCOMES[outcome], "att": np.nan,
                     "se": np.nan, "t": np.nan, "n_cells": 0, "n_treated": n_tr}); continue
    a,  s,  nc = overall_att(c)
    a0, s0, _  = overall_att(att_cells_nyt(Yk, Gk, drop_event0=True))
    rows.append({"outcome": outcome, "label": OUTCOMES[outcome], "att": a, "se": s,
                 "t": a/s if s else np.nan, "att_no_m0": a0, "se_no_m0": s0,
                 "t_no_m0": a0/s0 if s0 else np.nan, "n_cells": nc, "n_treated": n_tr})
    print(f"  {OUTCOMES[outcome]:<24} att {a:+.5f} ({s:.5f}) t={a/s:+.2f} | "
          f"no m0 {a0:+.5f} t={a0/s0:+.2f}", flush=True)

R = pd.DataFrame(rows)
R["significant"] = R["t"].abs() > 1.96
print("\n" + R[["label","att","se","t","att_no_m0","t_no_m0","n_cells","n_treated","significant"]]
      .to_string(index=False))

sm = R[R.outcome == "o5_self_merge_rate"]
if len(sm):
    v = float(sm["att"].iloc[0]); tv = float(sm["t"].iloc[0])
    print(f"\nSELF-MERGE: placebo {v:+.5f} (t={tv:+.2f})")
    print("Treatment B reference: +0.0234 to +0.0451 across the five safeguard types")
    print("VERDICT:", "NULL — gating mechanism holds" if abs(tv) < 1.96 else
          "SIGNIFICANT — adding any workflow moves merge authority; narrow the claim")

R.to_csv(os.path.join(RESULTS, "nb8_r1b_marginal_placebo.csv"), index=False)
json.dump(R.to_dict("records"), open(os.path.join(STATE, "nb8_armb4_summary.json"), "w"),
          indent=2, default=float)
print("\nwrote", os.path.join(RESULTS, "nb8_r1b_marginal_placebo.csv"))
