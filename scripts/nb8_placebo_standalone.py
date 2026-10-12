# =====================================================================
# Marginal non-gating placebo — COMPLETE, STANDALONE
#
#     %run /content/drive/MyDrive/peltzman/nb8_placebo_standalone.py
#
# Needs nothing from NB8. Mounts Drive, loads the panel, defines the estimator,
# verifies it against the published Treatment A values, then runs the placebo.
#
# Placebo design, matched to Treatment B:
#   population : never-gating repositories that already have a workflow
#   treatment  : the month they add ANOTHER workflow file, >= 3 months after the first
#   controls   : same population, not yet treated at t
#   eligibility: >= 12 months of repository history, adoption inside the window
#
# Treatment B self-merge reference: +0.0234 to +0.0451 across five safeguard types.
# =====================================================================
import os, sys, json, time, tempfile
import numpy as np, pandas as pd

try:
    from google.colab import drive; drive.mount("/content/drive", force_remount=False)
except Exception:
    pass

DRIVE   = "/content/drive/MyDrive/peltzman"
STATE   = os.path.join(DRIVE, "state")
RESULTS = os.path.join(DRIVE, "results")
RAW     = os.path.join(DRIVE, "raw")
os.makedirs(RESULTS, exist_ok=True)

SEED, N_BOOT, MIN_CELL = 20260101, 500, 10
MAX_LEAD, MAX_LAG      = 12, 24
NEVER_VALUE            = 1_000_000_000
GAP                    = 3

COL_REPO, COL_MONTH, COL_COHORT = "repo", "t", "g_A"
OUTCOMES = {
    "o3_review_coverage": "Review coverage", "o5_self_merge_rate": "Self-merge rate",
    "o6_direct_push_share": "Direct-push share", "o2_comments_per_pr": "Comments per PR",
    "o1_reviewers_per_pr": "Reviewers per PR", "o3b_changes_req_rate": "Changes-requested rate",
    "o4_churn_per_merged": "Change size", "o2b_reviews_per_pr": "Reviews per PR",
}
NB5_REF = {"o3_review_coverage": (0.0234123, 0.0033620),
           "o5_self_merge_rate": (0.0207347, 0.0036841)}

panel = pd.read_parquet(os.path.join(STATE, "nb4_panel_balanced.parquet"))
ALL_REPOS = panel[COL_REPO].drop_duplicates().sort_values().values
T0, TMAX  = int(panel[COL_MONTH].min()), int(panel[COL_MONTH].max())
print(f"panel {len(panel):,} rows | repos {len(ALL_REPOS):,} | months {T0}..{TMAX}")
def ym_to_t(y, m): return int(y) * 12 + (int(m) - 1)

# ------------------------------------------------------------------ estimator
def build_wide(outcome, cohort=None):
    Y = panel.pivot_table(index=COL_REPO, columns=COL_MONTH,
                          values=outcome, aggfunc="mean").reindex(ALL_REPOS)
    g = panel.groupby(COL_REPO)[cohort or COL_COHORT].first().reindex(ALL_REPOS)
    return Y, g.where(g.notna() & (g <= TMAX), NEVER_VALUE).astype("int64")

def _cells(Y, G, control_fn, drop_event0=False):
    N, cols = len(Y.index), list(Y.columns)
    cpos, cset = {c: j for j, c in enumerate(cols)}, set(cols)
    Yv, Gv, out = Y.values, G.values, {}
    for g in sorted(set(int(x) for x in Gv)):
        if g == NEVER_VALUE or (g - 1) not in cset: continue
        base, ing = Yv[:, cpos[g - 1]], (Gv == g)
        if ing.sum() < MIN_CELL: continue
        for t in cols:
            e = t - g
            if e < -MAX_LEAD or e > MAX_LAG or e == -1: continue
            if drop_event0 and e == 0: continue
            d = Yv[:, cpos[t]] - base
            ok = np.isfinite(d)
            ctl, m1 = control_fn(Gv, g, t) & ok, ing & ok
            n1, n0 = int(m1.sum()), int(ctl.sum())
            if n1 < MIN_CELL or n0 < MIN_CELL: continue
            a1, a0 = d[m1].mean(), d[ctl].mean()
            psi = np.zeros(N)
            psi[m1]  =  (d[m1]  - a1) * (N / n1)
            psi[ctl] = -(d[ctl] - a0) * (N / n0)
            out[(g, t)] = (float(a1 - a0), psi, n1)
    return out

never_ctl = lambda Gv, g, t: (Gv == NEVER_VALUE)
nyt_ctl   = lambda Gv, g, t: (Gv > max(t, g))

def overall(cells, drop=None):
    keys = [k for k in cells if k[1] >= k[0]]
    if not keys: return np.nan, np.nan, 0
    w = np.array([cells[k][2] for k in keys], float); w /= w.sum()
    att = float(sum(wi * cells[k][0] for wi, k in zip(w, keys)))
    psi = np.zeros_like(cells[keys[0]][1])
    for wi, k in zip(w, keys): psi += wi * cells[k][1]
    rng, kk = np.random.default_rng(SEED), (np.sqrt(5) + 1) / 2
    p, N = kk / np.sqrt(5), len(psi)
    draws = np.array([psi @ np.where(rng.random(N) < p, 1 - kk, kk) / N
                      for _ in range(N_BOOT)])
    return att, float(draws.std(ddof=1)), len(keys)

# --------------------------------------------------------------- sanity check
print("\n--- estimator check against the published Treatment A values ---")
for o, (ra, rs) in NB5_REF.items():
    Y, G = build_wide(o)
    a, s, _ = overall(_cells(Y, G, never_ctl))
    print(f"  {OUTCOMES[o]:<20} {a:+.5f} ({s:.5f})  paper {ra:+.5f} ({rs:.5f})"
          f"  dev {abs(a-ra)/rs:.2f} SE")

# ------------------------------------------------ marginal-workflow treatment
CACHE = os.path.join(STATE, "nb8_marginal_nongating.parquet")
controls = set(json.load(open(os.path.join(STATE, "nb1_controls.json"))))

if os.path.exists(CACHE):
    marg = pd.read_parquet(CACHE); print(f"\nreusing {CACHE} ({len(marg):,} repos)")
else:
    print("\nscanning workflows.csv.gz for file-version history ...")
    t0, parts, nrows = time.time(), [], 0
    for i, ch in enumerate(pd.read_csv(
            os.path.join(RAW, "workflows.csv.gz"),
            usecols=["repository","file_path","committed_date","valid_workflow"],
            chunksize=1_000_000, low_memory=False)):
        nrows += len(ch)
        ch = ch[ch["repository"].isin(controls)]
        if len(ch): ch = ch[ch["valid_workflow"].astype(str).str.lower().str.startswith("t")]
        if len(ch):
            ch = ch.assign(_d=pd.to_numeric(ch["committed_date"], errors="coerce")).dropna(subset=["_d"])
            parts.append(ch.groupby(["repository","file_path"], as_index=False)["_d"].min())
        print(f"  chunk {i:>3}  rows {nrows:>10,}  {time.time()-t0:6.0f}s", flush=True)
    fv = pd.concat(parts, ignore_index=True).groupby(
        ["repository","file_path"], as_index=False)["_d"].min()
    ts = pd.to_datetime(fv["_d"], unit="s", utc=True)
    fv["t"] = [ym_to_t(d.year, d.month) for d in ts]
    rows = []
    for repo, grp in fv.sort_values(["repository","t"]).groupby("repository", sort=False):
        tv = grp["t"].values; tf = int(tv[0]); later = tv[tv >= tf + GAP]
        rows.append({"repo": repo, "t_first": tf,
                     "t_marginal": int(later[0]) if len(later) else np.nan,
                     "n_files": len(grp)})
    marg = pd.DataFrame(rows); marg.to_parquet(CACHE, index=False)
    print(f"wrote {CACHE} ({len(marg):,} repos, {time.time()-t0:.0f}s)")

reps = pd.read_csv(os.path.join(RAW, "repositories.csv.gz"), usecols=["name","created"])
reps["created"] = pd.to_datetime(reps["created"], errors="coerce", utc=True)
reps["t_created"] = [ym_to_t(d.year, d.month) if pd.notna(d) else np.nan for d in reps["created"]]
marg = marg.merge(reps[["name","t_created"]], left_on="repo", right_on="name", how="left")

elig = marg["t_marginal"].notna() & marg["t_marginal"].between(T0, TMAX) & \
       ((marg["t_marginal"] - marg["t_created"]) >= 12)
gmap = dict(zip(marg.loc[elig,"repo"], marg.loc[elig,"t_marginal"].astype(int)))
pop  = set(marg.loc[marg["t_first"] <= TMAX, "repo"])
print(f"\nalready-automated never-gating repos : {len(pop):,}")
print(f"with a marginal workflow (gap>={GAP}m)   : {int(marg['t_marginal'].notna().sum()):,}")
print(f"eligible marginal adopters            : {len(gmap):,} | cohorts {len(set(gmap.values()))}")

# ------------------------------------------------------------------- estimate
print("\n--- placebo: adding another NON-GATING workflow ---")
rows = []
for o in OUTCOMES:
    Y, _ = build_wide(o)
    G = pd.Series([gmap.get(r, NEVER_VALUE) for r in Y.index], index=Y.index, dtype="int64")
    keep = np.array([r in pop for r in Y.index])
    Yk, Gk = Y[keep], G[keep]
    c = _cells(Yk, Gk, nyt_ctl)
    if not c:
        rows.append({"outcome": o, "label": OUTCOMES[o], "att": np.nan, "se": np.nan,
                     "t": np.nan, "n_cells": 0}); print(f"  {OUTCOMES[o]:<24} no cells"); continue
    a, s, nc  = overall(c)
    a0, s0, _ = overall(_cells(Yk, Gk, nyt_ctl, drop_event0=True))
    rows.append({"outcome": o, "label": OUTCOMES[o], "att": a, "se": s,
                 "t": a/s if s else np.nan, "att_no_m0": a0, "se_no_m0": s0,
                 "t_no_m0": a0/s0 if s0 else np.nan, "n_cells": nc,
                 "n_treated": int((Gk.values != NEVER_VALUE).sum())})
    print(f"  {OUTCOMES[o]:<24} att {a:+.5f} ({s:.5f}) t={a/s:+.2f} | "
          f"no m0 {a0:+.5f} t={a0/s0:+.2f}", flush=True)

R = pd.DataFrame(rows); R["significant"] = R["t"].abs() > 1.96
print("\n" + R[["label","att","se","t","att_no_m0","t_no_m0","n_cells","n_treated","significant"]]
      .to_string(index=False))

sm = R[R.outcome == "o5_self_merge_rate"]
if len(sm) and pd.notna(sm["t"].iloc[0]):
    v, tv = float(sm["att"].iloc[0]), float(sm["t"].iloc[0])
    print(f"\n{'='*64}\nSELF-MERGE placebo {v:+.5f}  t={tv:+.2f}")
    print("Treatment B reference: +0.0234 to +0.0451 (five safeguard types)")
    print("VERDICT:", "NULL — the gating mechanism holds" if abs(tv) < 1.96
          else "SIGNIFICANT — any added workflow moves merge authority; narrow the claim")
    print("="*64)

R.to_csv(os.path.join(RESULTS, "nb8_marginal_placebo.csv"), index=False)
json.dump(R.to_dict("records"),
          open(os.path.join(STATE, "nb8_marginal_placebo.json"), "w"), indent=2, default=float)
print("\nwrote", os.path.join(RESULTS, "nb8_marginal_placebo.csv"))
