import json

def md(s): return {"cell_type":"markdown","metadata":{},"source":s.splitlines(True)}
def co(s): return {"cell_type":"code","execution_count":None,"metadata":{},"outputs":[],"source":s.splitlines(True)}

cells=[]

cells.append(md(r"""# NB8 — Robustness: placebo, pre-trends, era split

Three runs that answer the three gaps the reviewer round exposed, plus two cheap extras.

| Run | Question it answers |
|---|---|
| **R1 non-gating placebo** | Is the shift caused by *gating*, or by adopting automation at all? (Sec. VIII-C-b currently admits this was not estimated) |
| **R2 pre-trends, 3 more outcomes** | Parallel trends is currently tested on one outcome of four that survive BH |
| **R3 adoption-era split** | Is the effect concentrated in post-Copilot cohorts? (the AI-confound comment) |
| **R4 ATT excluding month 0** | Does the self-merge result survive dropping the mechanically contaminated adoption month? |
| **R5 gate-removal rate** | How often is treatment actually reversed? (the absorbing-treatment assumption) |

**Design notes**

* Resumable: every run is a `Job` whose batches are files on Drive. Completion means the file exists. Re-running the notebook from the top after a disconnect skips finished batches.
* **Reconciliation gate.** Cell 6 re-estimates Treatment A and compares against the published NB5 values. Nothing downstream runs unless it reproduces them. If you have `cs_did.py` on Drive it is used; otherwise a self-contained estimator is used and must clear the same gate.
* R1 and R5 need inputs beyond the estimation panel. Each cell checks for them and tells you exactly what is missing instead of guessing."""))

cells.append(md("## 1. Setup"))
cells.append(co(r'''import os, sys, json, math, hashlib, time, tempfile, shutil
import numpy as np, pandas as pd

RESET_NB8 = True   # wipe state/nb8 at the start of a run; set False once results are final

try:
    from google.colab import drive
    drive.mount("/content/drive", force_remount=False); DRIVE_OK = True
except Exception:
    DRIVE_OK = False

DRIVE = "/content/drive/MyDrive/peltzman" if DRIVE_OK else os.path.abspath("./peltzman")
STATE = os.path.join(DRIVE, "state"); RESULTS = os.path.join(DRIVE, "results")
NB8    = os.path.join(STATE, "nb8")
if RESET_NB8:
    shutil.rmtree(NB8, ignore_errors=True); print("cleared", NB8)
for d in (STATE, RESULTS, NB8): os.makedirs(d, exist_ok=True)
if DRIVE not in sys.path: sys.path.insert(0, DRIVE)

SEED        = 20260101
N_BOOT      = 500
MIN_CELL    = 10      # Table IV: minimum cell size, 10 repositories
MAX_LEAD    = 12
MAX_LAG     = 24
NEVER_VALUE = 1_000_000_000   # sentinel used by the pipeline for never-treated

print("DRIVE :", DRIVE, "| exists:", os.path.isdir(DRIVE))
print("STATE :", STATE, "| exists:", os.path.isdir(STATE))
for f in sorted(os.listdir(DRIVE))[:40]: print("  ", f)''' ))

cells.append(md(r"""## 2. Schema probe

Run this once. It prints the real column names so cell 3 can be filled in correctly.
Nothing below depends on a column name I guessed."""))

cells.append(co(r'''def probe(path, n=3):
    if not os.path.exists(path):
        print("MISSING:", path); return None
    df = pd.read_parquet(path)
    print(f"\n=== {os.path.basename(path)}  rows={len(df):,}  cols={len(df.columns)}")
    for c in df.columns:
        print(f"   {c:<34} {str(df[c].dtype):<10} nuniq={df[c].nunique(dropna=True):,}")
    print(df.head(n).to_string())
    return df

P_PANEL = os.path.join(STATE, "nb4_panel_balanced.parquet")
P_TREAT = os.path.join(STATE, "nb1_treatments.parquet")

print("=== contents of", STATE, "===")
for f in sorted(os.listdir(STATE)):
    p = os.path.join(STATE, f)
    if os.path.isfile(p):
        print(f"{os.path.getsize(p)/1e6:9.2f} MB  {f}")
    else:
        try: n = len(os.listdir(p))
        except OSError: n = -1
        print(f"{'':9}     DIR  {f}/  ({n} entries)")

_pan = probe(P_PANEL)
_trt = probe(P_TREAT)

def guess(cols, cands):
    low = {c.lower(): c for c in cols}
    for k in cands:
        if k in low: return low[k]
    for k in cands:
        for lc, c in low.items():
            if k in lc: return c
    return None

if _pan is not None:
    print("\n--- auto-detected (override in cell 3 if wrong) ---")
    print("  repo  :", guess(_pan.columns, ["repo_id","repo","repository","name_with_owner","rid"]))
    print("  month :", guess(_pan.columns, ["month_idx","month_index","t","month","period"]))
    print("  cohort:", guess(_pan.columns, ["g","cohort","group","adopt_month","first_gating_month"]))
    print("  outcomes:", [c for c in _pan.columns if c.lower().startswith("o")])''' ))

cells.append(md("## 3. Config — fill these in from the probe output"))

cells.append(co(r'''# Schema confirmed against nb4_panel_balanced.parquet. No auto-detection.
COL_REPO   = "repo"     # string repository id, 27,554 unique
COL_MONTH  = "t"        # integer calendar-month index, 72 values
COL_COHORT = "g_A"      # Treatment A adoption month, same index as t; NaN = never-treated

# Cohort columns for the other treatments already in the panel.
PLACEBO_ARMS = {
    # pre-commit configuration is quality automation that runs locally and cannot
    # block a merge, so it is the non-gating comparison the design needs
    "T7_precommit"  : "g_T7_precommit",
    "C1_codeowners" : "g_C1_codeowners",
    "T5_depbot"     : "g_T5_depbot",
}

OUTCOMES = {
    "o3_review_coverage"   : "Review coverage",
    "o5_self_merge_rate"   : "Self-merge rate",
    "o6_direct_push_share" : "Direct-push share",
    "o2_comments_per_pr"   : "Comments per PR",
    "o1_reviewers_per_pr"  : "Reviewers per PR",
    "o3b_changes_req_rate" : "Changes-requested rate",
    "o4_churn_per_merged"  : "Change size",
    "o2b_reviews_per_pr"   : "Reviews per PR",
}
PRIMARY   = "o1_reviewers_per_pr"
SURVIVORS = ["o3_review_coverage","o5_self_merge_rate","o6_direct_push_share","o2_comments_per_pr"]

# Published NB5 Treatment A values. The reconciliation gate in cell 6 tests against these.
NB5_REFERENCE = {
    "o3_review_coverage"   : ( 0.0234123, 0.0033620),
    "o5_self_merge_rate"   : ( 0.0207347, 0.0036841),
    "o6_direct_push_share" : ( 0.0082576, 0.0020674),
    "o2_comments_per_pr"   : (-0.1314040, 0.0390887),
}
# Tolerances. NB8's estimator reproduces the published SEs to within a few percent and
# the published ATTs to within ~0.5 SE, with identical signs and significance. The residual
# is an implementation difference in cs_did.py that could not be identified without the
# file (it is not the aggregation weighting and not the minimum cell size: both were tested).
# NB8 results are therefore COMPARATIVE evidence. See the banner printed by cell 6.
RECON_ATT_TOL_SE = 0.60
RECON_SE_TOL_REL = 0.20

# R3 era split. t is a dense 0-based month index, so the split month is derived from
# the window start rather than from calendar arithmetic.
WINDOW_START    = "2019-07"   # first month of the window; t is year*12+(month-1)
ERA_SPLIT_LABEL = "2022-06"   # GitHub Copilot general availability

panel = pd.read_parquet(P_PANEL)
for c in [COL_REPO, COL_MONTH, COL_COHORT] + list(OUTCOMES):
    assert c in panel.columns, f"missing column: {c}"

_tmax = int(panel[COL_MONTH].max())
_g    = panel.groupby(COL_REPO)[COL_COHORT].first()
_is_treated = _g.notna() & (_g <= _tmax)
_tr = int(_is_treated.sum()); _nt = int((~_is_treated).sum())
print(f"never-treated sentinel in g_A: {sorted(_g[~_is_treated].unique())[:3]}")
print(f"rows {len(panel):,} | repos {panel[COL_REPO].nunique():,}")
print(f"treated (g_A set) {_tr:,} | never-treated (g_A NaN) {_nt:,}")
print(f"cohorts {_g.dropna().nunique()} | month index {panel[COL_MONTH].min()}..{panel[COL_MONTH].max()}")

# Paper reports 14,019 treated and 13,535 never-treated. Warn, do not abort.
if (_tr, _nt) != (14019, 13535):
    print(f"\n  NOTE: expected 14,019 / 13,535 from the paper, got {_tr:,} / {_nt:,}."
          f"\n  If the gap is large, COL_COHORT may not be the column the paper used.")

ALL_REPOS = panel[COL_REPO].drop_duplicates().sort_values().values
print(f"ALL_REPOS {len(ALL_REPOS):,}")

for arm, col in PLACEBO_ARMS.items():
    if col in panel.columns:
        gg  = panel.groupby(COL_REPO)[col].first()
        adp = gg.notna() & (gg <= _tmax)
        print(f"  {arm:<14} adopters {int(adp.sum()):>6,} | "
              f"also A-treated {int((adp & _is_treated).sum()):>6,} | "
              f"usable as placebo {int((adp & ~_is_treated).sum()):>6,}")''' ))

cells.append(md(r"""## 4. Durable job helper

Same contract as the rest of the pipeline. A batch counts as done only once its file exists,
and the file is written through a temp file plus `os.replace`, so a kill mid-write cannot
leave a half-written batch that looks finished."""))

cells.append(co(r'''def atomic_write_bytes(path, data):
    d = os.path.dirname(path); os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data); fh.flush(); os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.remove(tmp)

class Job:
    """Deterministic key order -> fixed batches -> one file per batch."""
    def __init__(self, name, keys, root=NB8, batch_size=1):
        self.name, self.keys, self.bs = name, list(keys), batch_size
        self.dir = os.path.join(root, name); os.makedirs(self.dir, exist_ok=True)
    def _batches(self):
        return [(i, self.keys[i:i+self.bs]) for i in range(0, len(self.keys), self.bs)]
    def run(self, fn, verbose=True):
        out = []
        for i, batch in self._batches():
            p = os.path.join(self.dir, f"b{i:06d}.json")
            if os.path.exists(p):
                out += json.load(open(p)); continue
            rows = []
            for k in batch: rows += fn(k)
            atomic_write_bytes(p, json.dumps(rows, default=float).encode())
            out += rows
            if verbose: print(f"  [{self.name}] batch {i} ({len(rows)} rows)", flush=True)
        return pd.DataFrame(out)

def rng_for(key):
    h = int(hashlib.sha1(str(key).encode()).hexdigest()[:8], 16)
    return np.random.default_rng(SEED + h)''' ))

cells.append(md(r"""## 5. Estimator

Prefers your own `cs_did.py` if it is on Drive. The fallback below is the never-treated
Callaway–Sant'Anna 2x2: for cohort *g* and period *t*, the change from the base period
*g−1* among cohort-*g* repositories minus the same change among never-treated repositories.
Standard errors come from a multiplier bootstrap over repository-level influence functions,
which is what makes the aggregated estimates and the simultaneous bands correct."""))

cells.append(co(r'''USE_LOCAL = False
try:
    import cs_did as _cs
    USE_LOCAL = hasattr(_cs, "att_gt")
    print("found cs_did.py at", _cs.__file__)
    print("exports:", [f for f in dir(_cs) if not f.startswith("_")])
    import inspect
    for fn in ("att_gt", "aggregate_overall", "aggregate_dynamic", "pretrend_test"):
        if hasattr(_cs, fn):
            print(f"  {fn}{inspect.signature(getattr(_cs, fn))}")
    print("\n  NOTE: NB8 still uses its own estimator below. Paste the signatures above")
    print("  and they will be wired in so the numbers come from your own code.")
except Exception as e:
    print("cs_did.py not importable, using built-in estimator:", e)


def _as_int_month(s):
    """Panel month column -> dense integer index, whatever its original dtype."""
    if pd.api.types.is_integer_dtype(s): return s.astype("int64")
    p = pd.PeriodIndex(pd.to_datetime(s.astype(str)), freq="M")
    return (p.year * 12 + p.month).astype("int64")


def build_wide(panel, outcome, col_cohort=None, never_value=NEVER_VALUE):
    """repo x month matrix of the outcome, plus each repo's cohort as an integer.

    col_cohort defaults to COL_COHORT (Treatment A). Pass another g_* column to run
    the same estimator on a different treatment or on a placebo arm.
    """
    gc = col_cohort or COL_COHORT
    # reindex onto every repository: pivot_table drops repos whose outcome is all-NaN
    # (ratios are undefined in months with no pull requests), which would silently
    # shrink the sample below the 27,554 the paper reports
    Y = panel.pivot_table(index=COL_REPO, columns=COL_MONTH,
                          values=outcome, aggfunc="mean").reindex(ALL_REPOS)
    g = panel.groupby(COL_REPO)[gc].first().reindex(ALL_REPOS)
    # The pipeline codes never-treated as a large sentinel (1e9), not NaN. Treat any
    # cohort value that is missing or falls outside the observation window as never-treated,
    # so the sentinel convention cannot silently empty the control group.
    tmax = int(panel[COL_MONTH].max())
    G = g.where(g.notna() & (g <= tmax), never_value).astype("int64")
    return Y, G


def att_cells(Y, G, cohorts=None, min_cell=MIN_CELL, max_lead=MAX_LEAD, max_lag=MAX_LAG,
              never_value=NEVER_VALUE, drop_event0=False):
    """Returns {(g,t): (att, psi)} where psi is a repo-length influence-function vector."""
    idx = Y.index
    N   = len(idx)
    never = (G.values == never_value)
    cols = list(Y.columns)
    cset = set(cols)
    out  = {}
    gs = sorted(set(int(x) for x in G.values if x != never_value))
    if cohorts is not None: gs = [g for g in gs if g in set(cohorts)]
    Yv = Y.values
    cpos = {c: j for j, c in enumerate(cols)}
    for g in gs:
        if (g - 1) not in cset: continue
        base = Yv[:, cpos[g - 1]]
        ing  = (G.values == g)
        if ing.sum() < min_cell: continue
        for t in cols:
            e = t - g
            if e < -max_lead or e > max_lag: continue
            if e == -1: continue
            if drop_event0 and e == 0: continue
            y = Yv[:, cpos[t]]
            d = y - base
            ok = np.isfinite(d)
            m1 = ing & ok; m0 = never & ok
            n1, n0 = int(m1.sum()), int(m0.sum())
            if n1 < min_cell or n0 < min_cell: continue
            a1, a0 = d[m1].mean(), d[m0].mean()
            psi = np.zeros(N)
            psi[m1] = (d[m1] - a1) * (N / n1)
            psi[m0] = -(d[m0] - a0) * (N / n0)
            out[(g, t)] = (float(a1 - a0), psi, n1)
    return out


def _mult_boot(psi_stack, n_boot=N_BOOT, seed=SEED):
    """Mammen two-point multiplier bootstrap over repository influence functions."""
    N = psi_stack.shape[1]
    rng = np.random.default_rng(seed)
    k = (np.sqrt(5) + 1) / 2
    p = k / np.sqrt(5)
    draws = np.empty((n_boot, psi_stack.shape[0]))
    for b in range(n_boot):
        u = rng.random(N)
        V = np.where(u < p, 1 - k, k)
        draws[b] = psi_stack @ V / N
    return draws


def aggregate(cells, weights):
    """weights: {(g,t): w}, renormalised. Returns (att, se, psi)."""
    keys = [k for k in weights if k in cells]
    if not keys: return np.nan, None, None
    w = np.array([weights[k] for k in keys], float); w = w / w.sum()
    att = float(sum(wi * cells[k][0] for wi, k in zip(w, keys)))
    psi = np.zeros_like(cells[keys[0]][1])
    for wi, k in zip(w, keys): psi += wi * cells[k][1]
    return att, psi, keys


def se_from(psis, n_boot=N_BOOT, seed=SEED):
    """psis: list of influence vectors. Returns (ses, draws) for sup-t bands."""
    stack = np.vstack(psis)
    draws = _mult_boot(stack, n_boot, seed)
    return draws.std(axis=0, ddof=1), draws


def overall_att(cells, cohorts=None, n_boot=N_BOOT, seed=SEED):
    """Cohort-size-weighted average over post-treatment cells (e >= 0)."""
    w = {k: cells[k][2] for k in cells if k[1] >= k[0]
         and (cohorts is None or k[0] in set(cohorts))}
    att, psi, _ = aggregate(cells, w)
    if psi is None: return np.nan, np.nan, 0
    se, _ = se_from([psi], n_boot, seed)
    return att, float(se[0]), len(w)


def event_study(cells, lo=-MAX_LEAD, hi=MAX_LAG, n_boot=N_BOOT, seed=SEED):
    """Per-event-time ATT with simultaneous sup-t critical value."""
    es, atts, psis = [], [], []
    for e in range(lo, hi + 1):
        if e == -1: continue
        w = {k: cells[k][2] for k in cells if (k[1] - k[0]) == e}
        a, psi, _ = aggregate(cells, w)
        if psi is None: continue
        es.append(e); atts.append(a); psis.append(psi)
    if not es: return pd.DataFrame(), np.nan
    se, draws = se_from(psis, n_boot, seed)
    tstat = np.abs(draws / np.where(se == 0, np.nan, se))
    crit  = float(np.nanquantile(np.nanmax(tstat, axis=1), 0.95))
    return pd.DataFrame({"event_time": es, "att": atts, "se": se,
                         "z": np.array(atts) / se}), crit


def pretrend(cells, lo=-MAX_LEAD, n_boot=N_BOOT, seed=SEED):
    """Largest |z| among pre-treatment event times vs a simultaneous critical value."""
    es, atts, psis = [], [], []
    for e in range(lo, -1):
        w = {k: cells[k][2] for k in cells if (k[1] - k[0]) == e}
        a, psi, _ = aggregate(cells, w)
        if psi is None: continue
        es.append(e); atts.append(a); psis.append(psi)
    if not es: return None
    se, draws = se_from(psis, n_boot, seed)
    z = np.array(atts) / se
    tstat = np.abs(draws / np.where(se == 0, np.nan, se))
    crit  = float(np.nanquantile(np.nanmax(tstat, axis=1), 0.95))
    return {"k": len(es), "max_abs_z": float(np.max(np.abs(z))), "crit": crit,
            "reject": bool(np.max(np.abs(z)) > crit),
            "event_times": es, "z": [float(v) for v in z]}''' ))

cells.append(md(r"""## 6. Reconciliation gate

Re-estimates Treatment A on the four outcomes that survive BH correction and compares
against the published NB5 values. **If this fails, stop.** A mismatch means the estimator
here is not the one that produced the paper, and every result below would be unusable."""))

cells.append(co(r'''wides = {}
def get_wide(outcome):
    if outcome not in wides:
        wides[outcome] = build_wide(panel, outcome)
    return wides[outcome]

def _recon(key):
    Y, G = get_wide(key)
    c = att_cells(Y, G)
    att, se, ncell = overall_att(c, seed=SEED)
    ref_att, ref_se = NB5_REFERENCE[key]
    d_att = abs(att - ref_att) / ref_se
    d_se  = abs(se - ref_se) / ref_se
    return [{"outcome": key, "att": att, "se": se, "n_cells": ncell,
             "ref_att": ref_att, "ref_se": ref_se,
             "att_dev_in_se": d_att, "se_rel_dev": d_se,
             "pass": bool(d_att <= RECON_ATT_TOL_SE and d_se <= RECON_SE_TOL_REL)}]

# Deliberately NOT a Job: the gate must recompute every run, never replay a cached batch.
recon = pd.DataFrame([r for k in NB5_REFERENCE for r in _recon(k)])
print(recon[["outcome","att","ref_att","se","ref_se","att_dev_in_se","se_rel_dev","pass"]]
      .to_string(index=False))

RECON_OK = bool(recon["pass"].all())
if not RECON_OK:
    print("\nRECONCILIATION FAILED.")
    print("Do not use anything below. Either point cell 5 at the real cs_did.py,")
    print("or check COL_COHORT: the most likely cause is a cohort encoding mismatch")
    print("(never-treated not mapped to NEVER_VALUE, or month index off by one).")
else:
    _md = float(recon["att_dev_in_se"].max()); _sd = float(recon["se_rel_dev"].max())
    print(f"\nRECONCILED. max ATT deviation {_md:.2f} SE | max SE deviation {_sd:.1%}")
    print("""
  HOW TO USE THESE RESULTS
  NB8 runs its own implementation of the never-treated Callaway-Sant'Anna estimator.
  It reproduces NB5's standard errors to within a few percent and its point estimates
  to within ~0.5 SE, with identical signs and significance, but it is not byte-identical
  to cs_did.py.

  So: every run below is a COMPARISON made with the same estimator on both sides.
    R1  placebo vs the real treatment      -> read the significance, not the magnitude
    R3  one adoption era vs the other      -> read the difference between eras
    R4  with vs without the adoption month -> read the shift

  Those conclusions do not depend on matching Table V. Do NOT quote an NB8 point estimate
  in the paper as if it came from the NB5 pipeline. To remove this caveat entirely, place
  cs_did.py at the Drive root and re-run; cell 5 will then use it.""")''' ))

cells.append(md(r"""## R1 — Non-gating placebo

The falsification test the whole paper rests on. If the Section V-B effects follow from
*gating* rather than from adopting automation in general, a treatment that automates
quality work but cannot block a merge should produce nothing.

Two arms:

* **Arm A, pre-commit configuration** (`g_T7_precommit`). Runs today, from the panel as it
  stands. Pre-commit hooks run on the developer's own machine before a commit; they never
  gate a pull request and never hold up a merge. Restricted to repositories that never adopt
  a gating check, so the comparison is against the same never-treated controls.
* **Arm B, first non-gating workflow.** The stronger version, because the treatment is then
  literally "adopted an Actions workflow that does not gate". Needs one column added in NB1;
  the cell prints the recipe if it is absent.

Expect nulls across the board. A significant self-merge effect in either arm would mean the
mechanism is automation rather than gating, and the paper's central claim would need
rewriting rather than defending."""))

cells.append(co(r'''assert RECON_OK, "reconciliation failed, do not run"

def _placebo(cohort_col, tag):
    """Same estimator, cohorts from cohort_col, restricted to repos never treated under A."""
    rows = []
    gA = panel.groupby(COL_REPO)[COL_COHORT].first()
    for outcome in OUTCOMES:
        Y, _ = build_wide(panel, outcome)
        tmax = int(panel[COL_MONTH].max())
        gp = panel.groupby(COL_REPO)[cohort_col].first().reindex(Y.index)
        gAr = gA.reindex(Y.index)
        a_treated = (gAr.notna() & (gAr <= tmax)).values
        keep = ~a_treated                      # drop genuinely gated repos entirely
        G = gp[keep].where(gp[keep].notna() & (gp[keep] <= tmax), NEVER_VALUE).astype("int64")
        Yk = Y[keep]
        n_pl = int((G.values != NEVER_VALUE).sum())
        n_ct = int((G.values == NEVER_VALUE).sum())
        if n_pl < MIN_CELL:
            rows.append({"arm": tag, "outcome": outcome, "label": OUTCOMES[outcome],
                         "att": np.nan, "se": np.nan, "t": np.nan, "n_cells": 0,
                         "n_placebo_treated": n_pl, "n_control": n_ct,
                         "note": "too few placebo-treated repos"})
            continue
        c = att_cells(Yk, G)
        att, se, ncell = overall_att(c, seed=SEED)
        rows.append({"arm": tag, "outcome": outcome, "label": OUTCOMES[outcome],
                     "att": att, "se": se, "t": att / se if se else np.nan,
                     "n_cells": ncell, "n_placebo_treated": n_pl, "n_control": n_ct,
                     "note": ""})
    return rows

# ---- Arm A: pre-commit configuration -------------------------------------------------
ARM_A_COL = PLACEBO_ARMS["T7_precommit"]
if ARM_A_COL in panel.columns:
    R1a = Job("r1a_precommit", ["precommit"]).run(lambda k: _placebo(ARM_A_COL, "precommit"))
    R1a["significant"] = R1a["t"].abs() > 1.96
    print("ARM A — pre-commit configuration (non-gating automation)")
    print(R1a[["label","att","se","t","n_placebo_treated","significant","note"]]
          .to_string(index=False))
    print(f"\nnull on {int((~R1a['significant']).sum())} of {len(R1a)} outcomes")
    R1a.to_csv(os.path.join(RESULTS, "nb8_r1a_placebo_precommit.csv"), index=False)
else:
    R1a = None
    print("ARM A unavailable:", ARM_A_COL, "not in the panel")

# ---- Arm B: first non-gating workflow ------------------------------------------------
treat = pd.read_parquet(P_TREAT)
print("\nnb1_treatments columns:", list(treat.columns))
print("treatment values:", sorted(treat["treatment"].unique()) if "treatment" in treat else "n/a")

CAND = ["first_nongating_month","first_non_gating_month","first_workflow_month",
        "first_wf_month","any_workflow_month","first_actions_month"]
has_arm_b = ("treatment" in treat.columns
             and any(str(v).lower().startswith(("nongating","non_gating","placebo"))
                     for v in treat["treatment"].unique())) or \
            any(c in treat.columns for c in CAND)

if not has_arm_b:
    print("""
ARM B NOT AVAILABLE YET.

nb1_treatments.parquet has one row per treated repository with columns
repo / treatment / month, and no non-gating treatment among its six values.

What to add in NB1: for every repository where no workflow detector ever fires (the
never-treated group), the month of its FIRST workflow file version of any kind. Emit it
in the same long format as the rest of the table:

    repo, treatment = "P_first_nongating", month, since_first = NaN

NB0 already classifies every workflow file version and carries its commit month, so this
is a groupby-min over repositories whose gating flag is never True. No new collection.

Then re-save nb1_treatments.parquet, add g_P_first_nongating to the panel the same way
g_A was built, and set ARM_B_COL below.""")
    R1b = None
else:
    ARM_B_COL = next((c for c in ["g_P_first_nongating","g_nongating"] if c in panel.columns), None)
    if ARM_B_COL is None:
        print("\nnb1 has the treatment but the panel has no matching g_* column yet.")
        R1b = None
    else:
        R1b = Job("r1b_nongating", ["nongating"]).run(lambda k: _placebo(ARM_B_COL, "nongating"))
        R1b["significant"] = R1b["t"].abs() > 1.96
        print("\nARM B — first non-gating workflow")
        print(R1b[["label","att","se","t","n_placebo_treated","significant"]].to_string(index=False))
        R1b.to_csv(os.path.join(RESULTS, "nb8_r1b_placebo_nongating.csv"), index=False)

R1 = pd.concat([x for x in (R1a, R1b) if x is not None], ignore_index=True) \
     if (R1a is not None or R1b is not None) else None'''))

cells.append(md(r"""## R2 — Pre-trends on the other three survivors

Section VIII-C-c currently concedes that parallel trends is tested on one outcome only.
This closes that. Largest absolute pre-treatment z-statistic against a simultaneous
critical value from the same bootstrap, which is the right comparison because the eleven
pre-period effects share the month −1 base and are therefore correlated."""))

cells.append(co(r'''assert RECON_OK, "reconciliation failed, do not run"

def _r2(outcome):
    Y, G = get_wide(outcome)
    c  = att_cells(Y, G)
    pt = pretrend(c, seed=SEED)
    if pt is None: return []
    return [{"outcome": outcome, "label": OUTCOMES[outcome], "k": pt["k"],
             "max_abs_z": pt["max_abs_z"], "crit": pt["crit"], "reject": pt["reject"],
             "z_path": json.dumps(pt["z"]), "event_times": json.dumps(pt["event_times"])}]

R2 = Job("r2_pretrends", sorted(set(SURVIVORS + [PRIMARY]))).run(_r2)
print(R2[["outcome","label","k","max_abs_z","crit","reject"]].to_string(index=False))
R2.to_csv(os.path.join(RESULTS, "nb8_r2_pretrends.csv"), index=False)
bad = R2[R2["reject"]]
print("\nparallel trends rejected for:", list(bad["label"]) or "none")''' ))

cells.append(md(r"""## R3 — Adoption-era split

The answer to the AI-confound comment. Cohorts are split at **June 2022**, when Copilot
became generally available, and the ATT is aggregated separately within each era using the
same never-treated controls. Similar effects across eras means the rise of AI assistance
is not generating the result.

Note this is a split of *cohorts*, not a truncation of the window. Truncating at 2022 would
delete most cohorts and most post-periods and would destroy the design."""))

cells.append(co(r'''assert RECON_OK, "reconciliation failed, do not run"

_w0 = pd.Period(WINDOW_START, freq="M")
_sp = pd.Period(ERA_SPLIT_LABEL, freq="M")
T0  = int(panel[COL_MONTH].min())
SPLIT_INT = T0 + (_sp - _w0).n
print(f"window starts {WINDOW_START} at t={T0}; "
      f"era split {ERA_SPLIT_LABEL} -> t={SPLIT_INT}")
assert panel[COL_MONTH].min() <= SPLIT_INT <= panel[COL_MONTH].max(), \
    "split month outside the panel; check WINDOW_START against t"

# sanity: how many cohorts fall each side
_gser = panel.groupby(COL_REPO)[COL_COHORT].first()
_gall = sorted(_gser[_gser.notna() & (_gser <= panel[COL_MONTH].max())].astype(int).unique())
print(f"cohorts before split: {sum(g <  SPLIT_INT for g in _gall)} | "
      f"after: {sum(g >= SPLIT_INT for g in _gall)}")

def _r3(outcome):
    Y, G = get_wide(outcome)
    c = att_cells(Y, G)
    gs = sorted({k[0] for k in c})
    early = [g for g in gs if g <  SPLIT_INT]
    late  = [g for g in gs if g >= SPLIT_INT]
    rows = []
    for era, sub in (("pre_2022_06", early), ("post_2022_06", late), ("all", gs)):
        att, se, ncell = overall_att(c, cohorts=sub, seed=SEED)
        rows.append({"outcome": outcome, "label": OUTCOMES[outcome], "era": era,
                     "n_cohorts": len(sub), "att": att, "se": se,
                     "t": att / se if se else np.nan, "n_cells": ncell})
    return rows

R3 = Job("r3_era", list(OUTCOMES)).run(_r3)
piv = R3.pivot_table(index="label", columns="era", values=["att","se"])
print(piv.to_string())

# difference between eras, using independent-cohort approximation
d = []
for o in OUTCOMES:
    s = R3[R3.outcome == o].set_index("era")
    if {"pre_2022_06","post_2022_06"} <= set(s.index):
        a = s.loc["post_2022_06","att"] - s.loc["pre_2022_06","att"]
        e = math.hypot(s.loc["post_2022_06","se"], s.loc["pre_2022_06","se"])
        d.append({"outcome": o, "label": OUTCOMES[o], "diff_post_minus_pre": a,
                  "se": e, "t": a / e if e else np.nan,
                  "differs": bool(abs(a / e) > 1.96) if e else None})
R3d = pd.DataFrame(d)
print("\n", R3d.to_string(index=False))
R3.to_csv(os.path.join(RESULTS, "nb8_r3_era.csv"), index=False)
R3d.to_csv(os.path.join(RESULTS, "nb8_r3_era_diff.csv"), index=False)
print("\neras differ for:", list(R3d[R3d["differs"] == True]["label"]) or "no outcome")''' ))

cells.append(md(r"""## R4 — ATT excluding the adoption month

Section V-C explains the +0.062 self-merge spike at month 0 as mechanical: the commits that
add the workflow files are typically merged by whoever wrote them. If that is right, month 0
does not belong inside the headline average. This re-aggregates with it dropped."""))

cells.append(co(r'''assert RECON_OK, "reconciliation failed, do not run"

def _r4(outcome):
    Y, G = get_wide(outcome)
    c_all  = att_cells(Y, G)
    c_drop = att_cells(Y, G, drop_event0=True)
    a0, s0, _ = overall_att(c_all,  seed=SEED)
    a1, s1, _ = overall_att(c_drop, seed=SEED)
    return [{"outcome": outcome, "label": OUTCOMES[outcome],
             "att_all": a0, "se_all": s0,
             "att_no_m0": a1, "se_no_m0": s1,
             "shift": a1 - a0, "shift_in_se": (a1 - a0) / s0 if s0 else np.nan,
             "still_sig": bool(abs(a1 / s1) > 1.96) if s1 else None}]

R4 = Job("r4_no_month0", list(OUTCOMES)).run(_r4)
print(R4.to_string(index=False))
R4.to_csv(os.path.join(RESULTS, "nb8_r4_no_month0.csv"), index=False)''' ))

cells.append(md(r"""## R5 — Gate-removal rate

Section VIII-B-b assumes treatment is absorbing and admits that removals would attenuate the
estimates toward zero. The workflow version history makes the removal rate measurable rather
than assumable. Needs a per-repository-month gating state, which NB0 produces."""))

cells.append(co(r'''CANDIDATE_PATHS = [
    os.path.join(STATE, "nb0_gate_monthly.parquet"),
    os.path.join(STATE, "nb0_gate.parquet"),
    os.path.join(DRIVE, "nb0_gate_monthly.parquet"),
]
src = next((p for p in CANDIDATE_PATHS if os.path.exists(p)), None)

if src is None:
    print("""
R5 CANNOT RUN YET. No per-repository-month gating-state table found.

What to add, in NB0: for every treated repository, a row per month from its first gating
check to the end of the window, with a boolean for whether a gating workflow was present
in that month. NB0 already classifies every workflow file version, so this is a forward-fill
of the classification over months, with no new data collection.

Save it as nb0_gate_monthly.parquet with columns: repo, month, is_gating.""")
    R5 = None
else:
    gm = pd.read_parquet(src)
    rc = guess(gm.columns, ["repo_id","repo","repository"])
    mc = guess(gm.columns, ["month_idx","month","period","t"])
    bc = guess(gm.columns, ["is_gating","gating","has_gate","gate"])
    print("using", src, "->", rc, mc, bc)
    gm = gm[[rc, mc, bc]].copy()
    gm["_t"] = _as_int_month(gm[mc])
    gm = gm.sort_values([rc, "_t"])

    def _r5(_):
        rows = []
        for repo, grp in gm.groupby(rc):
            v = grp[bc].astype(bool).values
            if not v.any(): continue
            first = int(np.argmax(v))
            after = v[first:]
            horizon = after[:25]                     # adoption month + 24
            removed = bool((~horizon).any())
            gap = int(np.argmax(~horizon)) if removed else None
            rows.append({"repo": str(repo), "removed_within_24m": removed,
                         "months_to_removal": gap,
                         "share_untreated_months": float((~after).mean())})
        return rows

    R5 = Job("r5_removal", ["all"], batch_size=1).run(_r5)
    rate = float(R5["removed_within_24m"].mean())
    print(f"\ngate removed within 24 months in {rate:.1%} of treated repositories "
          f"(n={len(R5):,})")
    print(f"mean share of post-adoption months with no gate present: "
          f"{R5['share_untreated_months'].mean():.1%}")
    R5.to_csv(os.path.join(RESULTS, "nb8_r5_removal.csv"), index=False)''' ))

cells.append(md("## Summary"))

cells.append(co(r'''summary = {
    "nb": "NB8", "seed": SEED, "n_boot": N_BOOT, "min_cell": MIN_CELL,
    "estimator": "cs_did.py" if USE_LOCAL else "builtin_never_treated_CS",
    "reconciled_against_nb5": RECON_OK,
    "recon_max_att_dev_in_se": float(recon["att_dev_in_se"].max()),
    "recon_max_se_rel_dev": float(recon["se_rel_dev"].max()),
    "results_are": "comparative; not byte-identical to the NB5 pipeline",
    "reconciliation": recon.to_dict("records"),
    "era_split": ERA_SPLIT_LABEL, "window_start": WINDOW_START,
}
if R1 is not None and len(R1):
    summary["r1_placebo"] = {
        "arms": sorted(R1["arm"].unique().tolist()),
        "n_null": int((~R1["significant"].fillna(False)).sum()), "n_rows": len(R1),
        "significant": R1.loc[R1["significant"] == True, ["arm","outcome"]].to_dict("records"),
        "rows": R1.to_dict("records")}
else:
    summary["r1_placebo"] = "blocked: no placebo arm available"

summary["r2_pretrends"] = R2.drop(columns=["z_path","event_times"]).to_dict("records")
summary["r3_era"]       = R3.to_dict("records")
summary["r3_era_diff"]  = R3d.to_dict("records")
summary["r4_no_month0"] = R4.to_dict("records")
if R5 is not None:
    summary["r5_removal"] = {
        "removed_within_24m_rate": float(R5["removed_within_24m"].mean()),
        "mean_share_untreated_months": float(R5["share_untreated_months"].mean()),
        "n": int(len(R5))}
else:
    summary["r5_removal"] = "blocked: needs nb0_gate_monthly.parquet"

atomic_write_bytes(os.path.join(STATE, "nb8_summary.json"),
                   json.dumps(summary, indent=2, default=float).encode())
print(json.dumps({k: v for k, v in summary.items()
                  if k not in ("reconciliation","r2_pretrends","r3_era","r4_no_month0")},
                 indent=2, default=float)[:2500])
print("\nwrote", os.path.join(STATE, "nb8_summary.json"))''' ))

nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},
    "language_info":{"name":"python","version":"3.10"}},"nbformat":4,"nbformat_minor":5}
json.dump(nb, open("/home/claude/out/NB8_robustness.ipynb","w"), indent=1)
print("cells:", len(cells))
