# =====================================================================
#  Peltzman Protocol — collect everything the paper needs, in one pass
#  Paste the printed output back. It also writes paper_data.json to
#  Drive in case you would rather attach the file.
# =====================================================================
import os, sys, json, gzip, csv, hashlib
from pathlib import Path
import numpy as np, pandas as pd

try:
    from google.colab import drive; drive.mount("/content/drive", force_remount=False)
    DRIVE = "/content/drive/MyDrive/peltzman"
except Exception:
    DRIVE = os.path.expanduser("~/peltzman_out")
STATE, RAW, OUT, FIG = (Path(DRIVE,"state"), Path(DRIVE,"raw"),
                        Path(DRIVE,"results"), Path(DRIVE,"figures"))
D = {}
def sec(name):
    print("\n" + "="*78); print(name); print("="*78)

def grab(key, fn, default=None):
    try:
        D[key] = fn(); return D[key]
    except Exception as e:
        D[key] = {"_error": f"{type(e).__name__}: {e}"}
        print(f"  [!] {key}: {type(e).__name__}: {e}")
        return default

def load_json(p):  return json.loads(Path(p).read_text())
def tab(df, n=60): return df.head(n).to_string(index=False, float_format=lambda x: f"{x:.6g}")

# ---------------------------------------------------------------- 1. files
sec("1 · ARTEFACT INVENTORY")
inv = []
for d in (STATE, OUT, FIG, RAW):
    if not d.exists(): continue
    for p in sorted(d.rglob("*")):
        if p.is_file() and p.stat().st_size > 0:
            inv.append({"path": str(p.relative_to(DRIVE)),
                        "mb": round(p.stat().st_size/2**20, 3)})
D["files"] = inv
for f in inv:
    if f["mb"] > 0.001: print(f"  {f['mb']:9.3f} MB  {f['path']}")

# ---------------------------------------------------- 2. saved summaries
sec("2 · NOTEBOOK SUMMARIES")
for key, fname in [("nb0b","nb0b_summary.json"), ("nb1","nb1_summary.json"),
                   ("nb2","nb2_summary.json"), ("nb3","nb3_summary.json"),
                   ("nb3b","nb3b_summary.json"), ("nb4","nb4_summary.json"),
                   ("nb5","nb5_summary.json")]:
    p = STATE/fname
    if p.exists():
        v = grab(key, lambda p=p: load_json(p))
        print(f"\n--- {fname}\n{json.dumps(v, indent=1, default=float)[:2500]}")
    else:
        print(f"\n--- {fname}: absent")

# ------------------------------------------------------- 3. sample frame
sec("3 · FRAME AND REPOSITORY CHARACTERISTICS")
def frame_chars():
    meta = {}
    with gzip.open(RAW/"repositories.csv.gz","rt",errors="replace") as f:
        for r in csv.DictReader(f):
            meta[r["name"]] = r
    tre = pd.read_parquet(STATE/"nb1_treatments.parquet")
    treated = set(tre[tre.treatment=="A_first_gating"].repo)
    never = set(json.loads((STATE/"nb1_controls.json").read_text()))
    def prof(names, label):
        sub = [meta[n] for n in names if n in meta]
        if not sub: return {}
        stars = np.array([float(s.get("stars") or 0) for s in sub])
        commits = np.array([float(s.get("commits") or 0) for s in sub])
        contrib = np.array([float(s.get("contributors") or 0) for s in sub])
        langs = pd.Series([s.get("language") or "?" for s in sub]).value_counts().head(10)
        created = pd.Series([(s.get("created") or "")[:4] for s in sub]).value_counts().sort_index()
        return {"n": len(sub),
                "stars": {"median": float(np.median(stars)), "p25": float(np.percentile(stars,25)),
                          "p75": float(np.percentile(stars,75)), "max": float(stars.max())},
                "commits_median": float(np.median(commits)),
                "contributors_median": float(np.median(contrib)),
                "top_languages": langs.to_dict(),
                "created_year": created.to_dict()}
    return {"all_metadata": len(meta),
            "treated": prof(treated,"treated"), "never_treated": prof(never,"never")}
fc = grab("frame", frame_chars, {})
if fc and "_error" not in fc:
    for arm in ("treated","never_treated"):
        a = fc.get(arm, {})
        if a: print(f"\n{arm}: n={a['n']:,} · stars median {a['stars']['median']:.0f} "
                    f"(IQR {a['stars']['p25']:.0f}–{a['stars']['p75']:.0f}, max {a['stars']['max']:.0f}) · "
                    f"commits median {a['commits_median']:.0f} · contributors median {a['contributors_median']:.0f}")
        if a: print(f"  languages: {a['top_languages']}")
        if a: print(f"  created:   {a['created_year']}")

# --------------------------------------------------------- 4. treatments
sec("4 · TREATMENT COHORTS")
def cohorts():
    tre = pd.read_parquet(STATE/"nb1_treatments.parquet")
    out = {}
    for t, sub in tre.groupby("treatment"):
        c = sub.month.value_counts().sort_index()
        out[t] = {"n_events": int(len(sub)), "n_repos": int(sub.repo.nunique()),
                  "n_months": int(len(c)), "first": str(c.index.min()),
                  "last": str(c.index.max()), "cohort_size_median": float(c.median()),
                  "cohort_size_max": int(c.max()),
                  "by_year": sub.month.str[:4].value_counts().sort_index().to_dict()}
    cfgp = STATE/"nb2_config_treatments.parquet"
    if cfgp.exists():
        cfg = pd.read_parquet(cfgp)
        for t, sub in cfg.groupby("treatment"):
            c = sub.month.value_counts().sort_index()
            out[t] = {"n_events": int(len(sub)), "n_repos": int(sub.repo.nunique()),
                      "n_months": int(len(c)), "first": str(c.index.min()),
                      "last": str(c.index.max()), "cohort_size_median": float(c.median()),
                      "by_arm": sub.arm.value_counts().to_dict() if "arm" in sub else {}}
    return out
ch = grab("cohorts", cohorts, {})
for t, v in (ch or {}).items():
    if "_error" in str(v): continue
    print(f"  {t:18s} {v['n_events']:6,} events · {v['n_repos']:6,} repos · "
          f"{v['n_months']:3d} months {v['first']}..{v['last']} · median cohort {v['cohort_size_median']:.0f}")

# ------------------------------------------------------------- 5. panels
sec("5 · PANEL AND OUTCOME DESCRIPTIVES")
def panel_desc():
    d = pd.read_parquet(STATE/"nb4_panel_balanced.parquet")
    OUTC = [c for c in d.columns if c.startswith(("o1_","o2_","o2b","o3_","o3b","o4_","o5_","o6_"))]
    NEVER = 10**9
    desc = {}
    for c in OUTC:
        v = d[c]
        desc[c] = {"coverage": float(v.notna().mean()), "mean": float(v.mean()),
                   "sd": float(v.std()), "median": float(v.median()),
                   "p10": float(v.quantile(.10)), "p90": float(v.quantile(.90))}
    tr = int((d.groupby("repo").g_A.min() < NEVER).sum())
    return {"n_rows": int(len(d)), "n_repos": int(d.repo.nunique()),
            "n_periods": int(d.tt.nunique()), "n_treated_repos": tr,
            "n_control_repos": int(d.repo.nunique()-tr), "outcomes": desc}
pd_ = grab("panel", panel_desc, {})
if pd_ and "_error" not in pd_:
    print(f"  {pd_['n_rows']:,} repo-months · {pd_['n_repos']:,} repos "
          f"({pd_['n_treated_repos']:,} treated / {pd_['n_control_repos']:,} control) · "
          f"{pd_['n_periods']} periods\n")
    print(f"  {'outcome':24s} {'cov':>6s} {'mean':>10s} {'sd':>10s} {'median':>10s} {'p10':>9s} {'p90':>9s}")
    for c, v in pd_["outcomes"].items():
        print(f"  {c:24s} {v['coverage']:6.1%} {v['mean']:10.4f} {v['sd']:10.4f} "
              f"{v['median']:10.4f} {v['p10']:9.4f} {v['p90']:9.4f}")

def raw_totals():
    p = STATE/"nb3_panel.parquet"
    df = pd.read_parquet(p)
    cols = [c for c in df.columns if c not in ("repo","month")]
    tot = {c: int(df[c].sum()) for c in cols if pd.api.types.is_numeric_dtype(df[c])}
    return {"n_rows": int(len(df)), "n_repos": int(df.repo.nunique()), "totals": tot}
rt = grab("event_totals", raw_totals, {})
if rt and "_error" not in rt:
    print(f"\n  event totals over the window ({rt['n_rows']:,} repo-months)")
    for k, v in sorted(rt["totals"].items()): print(f"    {k:26s} {v:>16,}")

# ---------------------------------------------------------- 6. bot shares
sec("6 · BOT CONTAMINATION")
def bots():
    df = pd.read_parquet(STATE/"nb3_panel.parquet")
    pairs = [("prs_opened","prs_opened_h"),("prs_merged","prs_merged_h"),
             ("reviews","reviews_h"),("reviewers","reviewers_h"),
             ("prs_reviewed","prs_reviewed_h"),("review_comments","review_comments_h"),
             ("self_merged","self_merged_h"),("pushes_default","pushes_default_h"),
             ("churn_merged","churn_merged_h")]
    share = {a: float(1-df[h].sum()/max(1,df[a].sum())) for a,h in pairs if h in df}
    by = df.groupby(df.month.str[:4])[["prs_opened","prs_opened_h"]].sum()
    yearly = (1-by.prs_opened_h/by.prs_opened).to_dict()
    return {"by_column": share, "pr_bot_share_by_year": {k: float(v) for k,v in yearly.items()}}
bt = grab("bots", bots, {})
if bt and "_error" not in bt:
    for k,v in bt["by_column"].items(): print(f"  {k:22s} bot share {v:7.2%}")
    print("\n  PRs opened, bot share by year")
    for k,v in bt["pr_bot_share_by_year"].items(): print(f"    {k}  {v:7.2%}")

# ------------------------------------------------------------ 7. results
sec("7 · RESULTS")
for key, fname in [("results_main","results_main.csv"),
                   ("results_multiplicity","results_multiplicity.csv"),
                   ("event_study","event_study.csv"),
                   ("mde","../state/nb4_mde.csv")]:
    p = (OUT/fname) if not fname.startswith("..") else (STATE/"nb4_mde.csv")
    if not p.exists(): print(f"\n--- {fname}: absent"); continue
    df = pd.read_csv(p)
    D[key] = df.to_dict(orient="records")
    print(f"\n--- {p.name}  ({len(df)} rows)")
    print(tab(df, 80))

# ------------------------------------------------- 8. reproducibility
sec("8 · REPRODUCIBILITY")
def repro():
    import platform
    mods = {}
    for m in ("numpy","pandas","pyarrow","yaml","matplotlib","requests"):
        try:
            mods[m] = __import__(m).__version__
        except Exception: mods[m] = "absent"
    hashes = {}
    for f in ("nb4_panel_balanced.parquet","nb3_panel.parquet","nb1_treatments.parquet"):
        p = STATE/f
        if p.exists():
            h = hashlib.sha256()
            with open(p,"rb") as fh:
                for blk in iter(lambda: fh.read(1<<20), b""): h.update(blk)
            hashes[f] = h.hexdigest()[:16]
    return {"python": platform.python_version(), "packages": mods, "sha256_16": hashes}
rp = grab("repro", repro, {})
print(json.dumps(rp, indent=1))

# ------------------------------------------------------------- write out
p = Path(DRIVE,"paper_data.json")
p.write_text(json.dumps(D, indent=1, default=float))
print("\n" + "="*78)
print(f"wrote {p}  ({p.stat().st_size/2**10:.0f} KB)")
print("Paste the output above. If it is truncated, attach paper_data.json instead.")
