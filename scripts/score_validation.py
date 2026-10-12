#!/usr/bin/env python3
"""
Score the detector-validation labelling.

    python score_validation.py detector_validation_labelled.xlsx nb7_validation_key.json

Both files are required. The workbook holds your labels; the key holds what the
classifier said, and was kept out of the workbook so the labelling stayed blind.
Download the key from Google Drive: peltzman/state/nb7_validation_key.json

Needs pandas and openpyxl:   pip install pandas openpyxl
Writes detector_validation_scored.csv and .json beside the workbook.
"""
import sys, json
from math import sqrt
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas is not installed.  pip install pandas openpyxl")

TRUNC_MARK = "… truncated …"


def kappa(a, b):
    """Cohen's kappa for two binary raters over the same items."""
    if len(a) == 0:
        return float("nan")
    po = float((a == b).mean())
    pe = sum(float((a == v).mean()) * float((b == v).mean()) for v in (0, 1))
    return (po - pe) / (1 - pe) if pe != 1 else float("nan")


def wilson(k, n, z=1.96):
    """Wilson score interval — correct at small n and near 0 or 1, where the
    textbook normal interval runs off the end of the scale."""
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return p, (c - h) / d, (c + h) / d


def main(xlsx, keyfile):
    lab = pd.read_excel(xlsx, sheet_name="Label")
    lab = lab[lab.row_id.astype(str).str.strip().str.isdigit()].copy()
    lab["row_id"] = lab.row_id.astype(int)

    key = json.loads(Path(keyfile).read_text())
    miss = [i for i in lab.row_id if str(i) not in key]
    if miss:
        sys.exit(f"{len(miss)} rows are absent from the key (first: {miss[:5]}). "
                 "The workbook and the key are from different runs of NB7.")
    lab["cls"]       = lab.row_id.map(lambda i: key[str(i)]["cls"])
    lab["stratum"]   = lab.row_id.map(lambda i: key[str(i)]["stratum"])
    lab["predicted"] = lab.row_id.map(lambda i: key[str(i)]["predicted"])
    lab["truncated"] = lab.workflow.astype(str).str.contains(TRUNC_MARK, regex=False)
    lab["LABEL"]     = lab.LABEL.astype(str).str.strip().str.lower()

    bad = lab[~lab.LABEL.isin(["yes", "no", "unclear"])]
    if len(bad):
        sys.exit(f"{len(bad)} rows are unlabelled or hold an unrecognised value "
                 f"(row_ids {list(bad.row_id)[:10]})")

    sanity = lab[lab.stratum.eq("positive") != lab.predicted.eq(1)]
    if len(sanity):
        print(f"WARNING: {len(sanity)} rows where stratum and prediction disagree — "
              "the key may be corrupt\n")

    unclear = lab[lab.LABEL == "unclear"]
    sc = lab[lab.LABEL.isin(["yes", "no"])].copy()
    sc["truth"] = (sc.LABEL == "yes").astype(int)

    print(f"{len(lab)} labelled · {len(unclear)} unclear (excluded) · {len(sc)} scored")
    print(f"{int(lab.truncated.sum())} of {len(lab)} rows were truncated at display time\n")

    print(f"{'class':16s} {'precision':>24s}  {'recall (lower bound)':>30s}")
    out = {}
    for c in sorted(sc.cls.unique()):
        pos = sc[(sc.cls == c) & (sc.stratum == "positive")]
        nm  = sc[(sc.cls == c) & (sc.stratum == "near_miss")]
        tp, npos = int(pos.truth.sum()), len(pos)
        fn, nnm  = int(nm.truth.sum()), len(nm)      # a near-miss judged yes IS a miss
        p, pl, ph = wilson(tp, npos)
        r, rl, rh = wilson(tp, tp + fn) if nnm > 0 else (float("nan"),) * 3
        out[c] = {"tp": tp, "n_pos": npos, "precision": p, "prec_ci": [pl, ph],
                  "fn_in_nearmiss": fn, "n_nearmiss": nnm,
                  "recall_lb": r, "recall_ci": [rl, rh]}
        rec = (f"{r:6.3f} [{rl:.3f},{rh:.3f}]  {fn} miss / {nnm}" if nnm > 0
               else "     n/a  no near-misses sampled")
        print(f"{c:16s} {p:6.3f} [{pl:.3f},{ph:.3f}] n={npos:<3d} {rec}")

    # --- pooled -----------------------------------------------------------
    P = sc[sc.stratum == "positive"]
    NM = sc[sc.stratum == "near_miss"]
    ptp, pn = int(P.truth.sum()), len(P)
    pfn = int(NM.truth.sum())
    pp, ppl, pph = wilson(ptp, pn)
    pr, prl, prh = wilson(ptp, ptp + pfn) if len(NM) else (float("nan"),) * 3
    print(f"\n{'POOLED':16s} {pp:6.3f} [{ppl:.3f},{pph:.3f}] n={pn:<3d} "
          f"{pr:6.3f} [{prl:.3f},{prh:.3f}]  {pfn} miss / {len(NM)}")

    # --- did truncation bias the labels? ----------------------------------
    print("\nTruncation check — precision on the predicted-positive stratum")
    trunc_split = {}
    for flag, name in ((False, "full file shown"), (True, "truncated at 4000 chars")):
        s = P[P.truncated == flag]
        k, n = int(s.truth.sum()), len(s)
        v, lo, hi = wilson(k, n)
        trunc_split[name] = {"k": k, "n": n, "precision": v, "ci": [lo, hi]}
        print(f"  {name:26s} {v:6.3f} [{lo:.3f},{hi:.3f}]  n={n}")
    a, b = trunc_split["full file shown"], trunc_split["truncated at 4000 chars"]
    if a["n"] and b["n"]:
        gap = a["precision"] - b["precision"]
        print(f"  gap {gap:+.3f} — " + (
            "truncation does not appear to have changed the labels"
            if abs(gap) < 0.10 else
            "TRUNCATED ROWS SCORE LOWER; report precision on the full-file rows as the "
            "estimate and the gap as a limitation"))

    # --- uniform-random negatives ----------------------------------------
    rnd = sc[sc.stratum == "random"]
    fp_rnd = int(rnd.truth.sum())
    print(f"\nUniform-random negatives judged YES: {fp_rnd} of {len(rnd)}")
    print("  " + ("zero — consistent with misses being confined to near-misses, "
                  "which is what makes the recall figure a valid lower bound"
                  if fp_rnd == 0 else
                  "NON-ZERO — misses are not confined to near-misses, so the recall "
                  "above is NOT a lower bound. Report it as an estimate on the "
                  "near-miss stratum only."))

    agree = float((sc.truth == sc.predicted).mean())
    kap = kappa(sc.truth, sc.predicted)
    full = sc[~sc.truncated]
    agree_full = float((full.truth == full.predicted).mean())
    kap_full = kappa(full.truth, full.predicted)
    print(f"\nAgreement, labeller vs classifier")
    print(f"  all scorable            {agree:.3f}  kappa {kap:.3f}  n={len(sc)}")
    print(f"  full text visible       {agree_full:.3f}  kappa {kap_full:.3f}  n={len(full)}")

    # --- Table II as published ------------------------------------------
    # The table reports precision on the predicted-positive rows whose full
    # text the labeller could see, since a truncated file cannot be judged
    # against its own tail. The pooled figure over every predicted-positive
    # row, truncated included, is printed above and is the conservative
    # reading quoted in the text.
    print("\nTable II: precision on predicted-positive rows, full text visible")
    PF = sc[(sc.stratum == "positive") & (~sc.truncated)]
    table2 = {}
    for c in sorted(PF.cls.unique()):
        s = PF[PF.cls == c]
        v, lo, hi = wilson(int(s.truth.sum()), len(s))
        table2[c] = {"precision": v, "ci": [lo, hi], "n": len(s)}
        print(f"  {c:16s} {v:6.3f} [{lo:.3f},{hi:.3f}] n={len(s)}")
    v, lo, hi = wilson(int(PF.truth.sum()), len(PF))
    table2["POOLED"] = {"precision": v, "ci": [lo, hi], "n": len(PF)}
    print(f"  {'POOLED':16s} {v:6.3f} [{lo:.3f},{hi:.3f}] n={len(PF)}")

    res = {"per_class": out,
           "pooled": {"precision": pp, "prec_ci": [ppl, pph], "n_pos": pn,
                      "recall_lb": pr, "recall_ci": [prl, prh],
                      "fn_in_nearmiss": pfn, "n_nearmiss": len(NM)},
           "truncation": trunc_split,
           "n_labelled": int(len(lab)), "n_unclear": int(len(unclear)),
           "n_scored": int(len(sc)), "n_truncated": int(lab.truncated.sum()),
           "random_negatives_yes": fp_rnd, "n_random": int(len(rnd)),
           "raw_agreement": agree, "kappa": kap,
           "raw_agreement_full_text": agree_full, "kappa_full_text": kap_full,
           "n_full_text": int(len(full)), "table2": table2}

    stem = Path(xlsx).with_suffix("")
    pd.DataFrame(out).T.to_csv(f"{stem}_scored.csv")
    Path(f"{stem}_scored.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"\nwrote {stem}_scored.csv and {stem}_scored.json")
    print("\n--- paste everything above this line ---")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
