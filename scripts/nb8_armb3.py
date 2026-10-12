# =====================================================================
# NB8 Arm B (v3) — is the placebo's self-merge effect mechanical or behavioural?
#
#     %run /content/drive/MyDrive/peltzman/nb8_armb3.py
#
# The placebo's treatment event is "the repository's first workflow file appears".
# The pull request that ADDS that file is typically merged by its own author, so a
# self-merge bump in the adoption month is mechanical, not behavioural. Treatment A
# has the same artefact (Sec. V-C) and survives it: +0.0188 -> +0.0162 once month 0
# is dropped, still significant.
#
# Decisive comparison: the shape of the event-study path, and what survives dropping
# the adoption month, for the placebo versus the real treatment, side by side.
# =====================================================================
import os, json
import numpy as np, pandas as pd

PARQ = os.path.join(STATE, "nb8_nongating_first.parquet")
T0, TMAX = int(panel[COL_MONTH].min()), int(panel[COL_MONTH].max())
def ym_to_t(y, m): return int(y) * 12 + (int(m) - 1)

first = pd.read_parquet(PARQ)
reps  = pd.read_csv("/content/drive/MyDrive/peltzman/raw/repositories.csv.gz",
                    usecols=["name","created"])
reps["created"] = pd.to_datetime(reps["created"], errors="coerce", utc=True)
reps["t_created"] = [ym_to_t(d.year, d.month) if pd.notna(d) else np.nan
                     for d in reps["created"]]
first = first.merge(reps[["name","t_created"]], left_on="repo", right_on="name", how="left")
elig  = first["t_first"].between(T0, TMAX) & ((first["t_first"] - first["t_created"]) >= 12)
gmap  = dict(zip(first.loc[elig,"repo"], first.loc[elig,"t_first"].astype(int)))

FOCUS = ["o5_self_merge_rate", "o6_direct_push_share"]
summary = {}

for outcome in FOCUS:
    print(f"\n{'='*66}\n{OUTCOMES[outcome]}\n{'='*66}")

    # ---------- placebo, not-yet-treated controls ----------
    Y, _ = build_wide(panel, outcome)
    Gp   = pd.Series([gmap.get(r, NEVER_VALUE) for r in Y.index], index=Y.index, dtype="int64")
    keep = Gp.values != NEVER_VALUE
    cP   = att_cells_nyt(Y[keep], Gp[keep])
    cP0  = att_cells_nyt(Y[keep], Gp[keep], drop_event0=True)

    # ---------- real treatment, never-treated controls ----------
    Yr, Gr = build_wide(panel, outcome)
    cA   = att_cells(Yr, Gr, never_value=NEVER_VALUE)
    cA0  = att_cells(Yr, Gr, never_value=NEVER_VALUE, drop_event0=True)

    aP,  sP,  _ = overall_att(cP);   aP0, sP0, _ = overall_att(cP0)
    aA,  sA,  _ = overall_att(cA);   aA0, sA0, _ = overall_att(cA0)
    print(f"  placebo   all {aP:+.5f} ({sP:.5f}) t={aP/sP:+.2f}   "
          f"no month0 {aP0:+.5f} ({sP0:.5f}) t={aP0/sP0:+.2f}")
    print(f"  real      all {aA:+.5f} ({sA:.5f}) t={aA/sA:+.2f}   "
          f"no month0 {aA0:+.5f} ({sA0:.5f}) t={aA0/sA0:+.2f}")
    print(f"  placebo retains {100*aP0/aP:5.1f}% of its effect | "
          f"real retains {100*aA0/aA:5.1f}%")

    # ---------- event-study paths, side by side ----------
    esP, _ = event_study(cP); esA, _ = event_study(cA)
    m = esP.merge(esA, on="event_time", suffixes=("_placebo", "_real"))
    print("\n  event-time   placebo ATT (se)        real ATT (se)")
    for _, r in m.iterrows():
        e = int(r.event_time)
        if e in (-12,-6,-3,-1,0,1,2,3,6,12,18,24):
            print(f"    {e:>4}      {r.att_placebo:+.5f} ({r.se_placebo:.5f})   "
                  f"{r.att_real:+.5f} ({r.se_real:.5f})")

    # plateau = mean of event times 6..24
    pl = m[m.event_time.between(6, 24)]
    plP, plA = pl["att_placebo"].mean(), pl["att_real"].mean()
    sp = m.loc[m.event_time == 0]
    spP = float(sp["att_placebo"].iloc[0]) if len(sp) else np.nan
    spA = float(sp["att_real"].iloc[0])    if len(sp) else np.nan
    print(f"\n  month-0 spike   placebo {spP:+.5f} | real {spA:+.5f}")
    print(f"  plateau (6-24)  placebo {plP:+.5f} | real {plA:+.5f}")
    print(f"  plateau/spike   placebo {plP/spP if spP else float('nan'):.2f} | "
          f"real {plA/spA if spA else float('nan'):.2f}")
    verdict = ("MECHANICAL: placebo collapses once the adoption month is removed"
               if abs(plP) < 0.35 * abs(plA) else
               "BEHAVIOURAL: placebo sustains a plateau comparable to the real effect")
    print(f"\n  -> {verdict}")

    summary[outcome] = {
        "placebo_all": aP, "placebo_se": sP, "placebo_no_m0": aP0, "placebo_no_m0_se": sP0,
        "real_all": aA, "real_se": sA, "real_no_m0": aA0, "real_no_m0_se": sA0,
        "placebo_spike": spP, "real_spike": spA,
        "placebo_plateau": plP, "real_plateau": plA, "verdict": verdict}
    m.to_csv(os.path.join(RESULTS, f"nb8_armb3_path_{outcome}.csv"), index=False)

json.dump(summary, open(os.path.join(STATE, "nb8_armb3_summary.json"), "w"),
          indent=2, default=float)
print("\nwrote", os.path.join(STATE, "nb8_armb3_summary.json"))
