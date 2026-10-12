# =====================================================================
# NB8 Arm B — non-gating placebo
#
# Run AFTER NB8 cells 1-6 (needs panel, att_cells, overall_att, build_wide,
# OUTCOMES, NEVER_VALUE, STATE, RESULTS, SEED in the namespace):
#
#     %run /content/drive/MyDrive/peltzman/nb8_armb.py
#
# Treatment : among repositories where no gating detector ever fires, the month
#             the repository's FIRST workflow file version appears.
# Controls  : never-gating repositories whose first workflow predates the window,
#             i.e. stably automated with no adoption event inside the window.
#             (The dataset only covers repositories that have workflows, so a
#             never-automated control group does not exist.)
# Eligibility: same two rules as Treatment A. At least twelve months of repository
#             history before adoption, and adoption inside the window.
# =====================================================================
import os, gzip, json, time
import numpy as np, pandas as pd

RAW       = "/content/drive/MyDrive/peltzman/raw"
WF_CSV    = os.path.join(RAW, "workflows.csv.gz")
REPO_CSV  = os.path.join(RAW, "repositories.csv.gz")
OUT_PARQ  = os.path.join(STATE, "nb8_nongating_first.parquet")
CHUNK     = 1_000_000

T0   = int(panel[COL_MONTH].min())      # 2019-07
TMAX = int(panel[COL_MONTH].max())      # 2025-06
def ym_to_t(y, m): return int(y) * 12 + (int(m) - 1)

# ---------------------------------------------------------------- 1. controls
controls = set(json.load(open(os.path.join(STATE, "nb1_controls.json"))))
panel_never = set(panel.groupby(COL_REPO)[COL_COHORT].first()
                  .pipe(lambda s: s[~(s.notna() & (s <= TMAX))]).index)
print(f"never-gating repos: {len(controls):,} in nb1_controls | "
      f"{len(panel_never):,} in the panel")

# ------------------------------------------- 2. first workflow month per repo
if os.path.exists(OUT_PARQ):
    first = pd.read_parquet(OUT_PARQ)
    print(f"reusing {OUT_PARQ} ({len(first):,} repos)")
else:
    t_start = time.time()
    best, nrows = {}, 0
    reader = pd.read_csv(WF_CSV, usecols=["repository", "committed_date", "valid_workflow"],
                         chunksize=CHUNK, low_memory=False)
    for i, ch in enumerate(reader):
        nrows += len(ch)
        ch = ch[ch["repository"].isin(controls)]
        if len(ch):
            vw = ch["valid_workflow"].astype(str).str.lower().str.startswith("t")
            ch = ch[vw]
        if len(ch):
            d = pd.to_numeric(ch["committed_date"], errors="coerce")
            ch = ch.assign(_d=d).dropna(subset=["_d"])
            for r, v in ch.groupby("repository")["_d"].min().items():
                if r not in best or v < best[r]: best[r] = v
        if i % 1 == 0:
            print(f"  chunk {i:>3}  rows {nrows:>10,}  repos found {len(best):>7,}"
                  f"  {time.time()-t_start:6.0f}s", flush=True)
    ts = pd.to_datetime(pd.Series(best), unit="s", utc=True)
    first = pd.DataFrame({"repo": list(best), "first_ts": ts.values})
    first["t_first"] = [ym_to_t(d.year, d.month) for d in first["first_ts"]]
    first.to_parquet(OUT_PARQ, index=False)
    print(f"wrote {OUT_PARQ}  ({len(first):,} repos, {time.time()-t_start:.0f}s)")

# --------------------------------------------------- 3. eligibility and groups
reps = pd.read_csv(REPO_CSV, usecols=["name", "created", "stars", "commits", "contributors"])
reps["created"] = pd.to_datetime(reps["created"], errors="coerce", utc=True)
reps["t_created"] = [ym_to_t(d.year, d.month) if pd.notna(d) else np.nan
                     for d in reps["created"]]
first = first.merge(reps[["name", "t_created"]], left_on="repo", right_on="name", how="left")

in_window  = first["t_first"].between(T0, TMAX)
old_enough = (first["t_first"] - first["t_created"]) >= 12
pre_window = first["t_first"] < T0

first["group"] = np.where(in_window & old_enough, "placebo_treated",
                  np.where(pre_window, "control", "excluded"))
print("\n" + first["group"].value_counts().to_string())

gmap = dict(zip(first.loc[first.group == "placebo_treated", "repo"],
                first.loc[first.group == "placebo_treated", "t_first"].astype(int)))
ctrl = set(first.loc[first.group == "control", "repo"])
print(f"\nplacebo-treated {len(gmap):,} | controls {len(ctrl):,} | "
      f"cohorts {len(set(gmap.values()))}")

# ------------------------------------------------------------- 4. estimate
rows = []
for outcome in OUTCOMES:
    Y, _ = build_wide(panel, outcome)
    idx  = Y.index
    G    = pd.Series(NEVER_VALUE, index=idx, dtype="int64")
    keep = np.zeros(len(idx), dtype=bool)
    for j, r in enumerate(idx):
        if r in gmap:   G.iloc[j] = gmap[r]; keep[j] = True
        elif r in ctrl: keep[j] = True
    Yk, Gk = Y[keep], G[keep]
    n_pl = int((Gk.values != NEVER_VALUE).sum()); n_ct = int((Gk.values == NEVER_VALUE).sum())
    if n_pl < MIN_CELL or n_ct < MIN_CELL:
        rows.append({"outcome": outcome, "label": OUTCOMES[outcome], "att": np.nan,
                     "se": np.nan, "t": np.nan, "n_cells": 0,
                     "n_placebo_treated": n_pl, "n_control": n_ct}); continue
    c = att_cells(Yk, Gk, never_value=NEVER_VALUE)
    att, se, ncell = overall_att(c)
    rows.append({"outcome": outcome, "label": OUTCOMES[outcome], "att": att, "se": se,
                 "t": att / se if se else np.nan, "n_cells": ncell,
                 "n_placebo_treated": n_pl, "n_control": n_ct})
    print(f"  {OUTCOMES[outcome]:<24} att {att:+.5f}  se {se:.5f}  "
          f"t {att/se if se else float('nan'):+.2f}  cells {ncell}", flush=True)

R1b = pd.DataFrame(rows)
R1b["significant"] = R1b["t"].abs() > 1.96
print("\n" + R1b[["label","att","se","t","n_cells","n_placebo_treated","significant"]]
      .to_string(index=False))
sig = R1b.loc[R1b["significant"] == True, "label"].tolist()
print(f"\nnull on {int((R1b['significant'] == False).sum())} of {len(R1b)} outcomes")
print("significant:", sig or "none")
R1b.to_csv(os.path.join(RESULTS, "nb8_r1b_placebo_nongating.csv"), index=False)

json.dump({"placebo_treated": len(gmap), "controls": len(ctrl),
           "cohorts": len(set(gmap.values())),
           "significant": sig, "rows": R1b.to_dict("records")},
          open(os.path.join(STATE, "nb8_r1b_summary.json"), "w"), indent=2, default=float)
print("wrote", os.path.join(RESULTS, "nb8_r1b_placebo_nongating.csv"))
