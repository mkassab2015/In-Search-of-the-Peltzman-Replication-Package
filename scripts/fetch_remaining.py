#!/usr/bin/env python3
"""Copy files from the working folder into the package layout.

This package is complete: every number in the paper traces to a file already
here. The script is kept because it is how the package was assembled and is
the quickest way to refresh a file after rerunning a stage, or to pull in the
optional upstream panels that were left out for size.

Unlike collect_package.py, which matches globs, this works from an explicit
named inventory: every file is listed with the notebook that writes it, the
claim it supports, and whether the package is incomplete without it. It
copies what it finds, names what it does not, and exits non-zero if anything
required is absent.

In Colab:
    from google.colab import drive; drive.mount('/content/drive')
    !python scripts/fetch_remaining.py \
        --source /content/drive/MyDrive/peltzman --dest .

Locally:
    python scripts/fetch_remaining.py --source ~/peltzman --dest .

Add --dry-run to see what would be copied without copying it.
"""
import argparse
import os
import shutil
import sys

# (source subdir, filename, dest subdir, written by, supports, required)
# An optional seventh element renames the file at its destination.
REQ, OPT = True, False
INVENTORY = [
    # ---- the derived panel -------------------------------------------------
    ("state", "nb4_panel_balanced.parquet", "data/derived",
     "NB4_panel_power", "every estimate in Tables IV, V and VI", REQ),
    ("state", "nb3_panel.parquet", "data/derived",
     "NB3_panel", "the eight outcomes, Table III", OPT),
    ("state", "nb3_panel_rawbots.parquet", "data/derived",
     "NB3b_panel_human", "Table VI Panel B, bots counted in", OPT),
    ("state", "nb1_treatments.parquet", "data/derived",
     "NB1_treatments", "first adoption per repository", OPT),
    ("state", "nb2_config_treatments.parquet", "data/derived",
     "NB2_configs", "Treatment B arms, Table V", OPT),
    ("state", "nb0_gate.parquet", "data/derived",
     "NB0_gate", "the repository frame", OPT),
    ("state", "nb0_gate_monthly.parquet", "data/derived",
     "NB0_gate", "monthly frame counts", OPT),

    # ---- the validation labels and the held-out key -------------------------
    # The copy in peltzman/results is the BLANK instrument; the labeled one
    # is elsewhere. Point --source at wherever it is, or pass the workbook to
    # score_validation.py directly. See MISSING.md.
    ("results", "detector_validation_labelled.xlsx", "data",
     "NB7_detector_validation, then labeled by hand", "Table II", OPT),
    ("state", "nb7_validation_key.json", "state",
     "NB7_detector_validation", "Table II, joined to the labels at scoring", REQ),
    ("state", "nb7_sample.json", "state",
     "NB7_detector_validation", "the sampling design behind Table II", OPT),
    ("state", "nb7_sample_repos.json", "state",
     "NB7_detector_validation", "provenance of the 175 sampled files", OPT),
    ("results", "nb7_validation.json", "results",
     "NB7_detector_validation", "the scored result, Table II", OPT),

    # ---- Section VI outputs, absent from this copy --------------------------
    ("results", "nb8_r1a_placebo_precommit.csv", "results",
     "NB8_robustness R1", "Check 3, pre-commit placebo", REQ),
    ("results", "nb8_r1b_placebo_nongating.csv", "results",
     "NB8_robustness R1", "Check 3, non-gating placebo, Panel C", REQ),
    ("results", "nb8_r1b_placebo_nyt.csv", "results",
     "scripts/nb8_armb2.py", "Check 3, Panel C differences", REQ),
    ("results", "nb8_marginal_placebo.csv", "results",
     "scripts/nb8_placebo_standalone.py", "Check 3, the reported placebo estimate", REQ),
    ("results", "nb8_r1b_marginal_placebo.csv", "results",
     "scripts/nb8_armb4.py",
     "an earlier run of the same arm, superseded by nb8_marginal_placebo.csv", OPT),
    ("results", "nb8_r2_pretrends.csv", "results",
     "NB8_robustness R2", "Check 4, Panel D, five pre-trend tests", REQ),
    ("results", "nb8_r3_era.csv", "results",
     "NB8_robustness R3", "Check 4, era split at June 2022, per-era ATT", OPT),
    ("results", "nb8_r3_era_diff.csv", "results",
     "NB8_robustness R3", "Check 4, era difference, t = -0.54", REQ),
    ("results", "nb8_r4_no_month0.csv", "results",
     "NB8_robustness R4", "ATT excluding the adoption month", REQ),
    # R5 was blocked on nb0_gate_monthly.parquet and never produced this
    # file; nb8_summary.json records the status. See MISSING.md.
    ("results", "nb8_r5_removal.csv", "results",
     "NB8_robustness R5", "gate-removal rate; R5 did not run, see MISSING.md", OPT),
    ("state", "nb0_gate_monthly.parquet", "data/derived",
     "NB0_gate", "the input R5 needs", OPT),
    ("results", "nb8_armb3_path_o5_self_merge_rate.csv", "results",
     "scripts/nb8_armb3.py", "Figure 3", REQ),
    ("results", "nb8_armb3_path_o1_reviewers_per_pr.csv", "results",
     "scripts/nb8_armb3.py", "Figure 3, other outcomes", OPT),
    ("results", "nb8_armb3_path_o3_review_coverage.csv", "results",
     "scripts/nb8_armb3.py", "Figure 3, other outcomes", OPT),
    ("results", "nb4_mde.csv", "results",
     "NB4_panel_power", "minimum detectable effect, Section V-B", REQ),

    # ---- the per-stage summaries that carry the reported counts --------------
    ("state", "gateC.json", "results", "NB0_gate", "frame size, 54,758", OPT),
    ("state", "nb1_summary.json", "results", "NB1_treatments", "corpus counts", OPT),
    ("state", "nb2_summary.json", "results", "NB2_configs",
     "45.2 / 18.0 / 36.8 percent split, 3.7M file versions", OPT),
    ("state", "nb3_summary.json", "results", "NB3_panel", "outcome means, Table III", OPT),
    ("state", "nb3b_summary.json", "results", "NB3b_panel_human", "human-only means", OPT),
    ("state", "nb4_summary.json", "results", "NB4_panel_power",
     "panel size 1,678,508 rows over 27,554 repos, 17.1 percent inactive", OPT),
    ("state", "nb5_summary.json", "results", "NB5_estimation",
     "randomization centre, pre-trend z, BH outcome", OPT),
    ("state", "nb6_summary.json", "results", "NB6_bots_and_eventstudies",
     "sign test, bot shares", OPT),
    ("state", "nb8_summary.json", "results", "NB8_robustness", "Table VI", OPT),
    ("state", "nb1_controls.json", "state", "NB1_treatments", "the control set", OPT),
    ("state", "nb1_first_seen.json", "state", "NB1_treatments", "first-seen months", OPT),

    # ---- the one notebook that is not here ----------------------------------
    (".", "NB0b_bundling.ipynb", "notebooks", "hand-run",
     "71.7 percent bundled within three months, Section IV", OPT),
]

EXTRA_NOTEBOOK_DIRS = ["", "notebooks", "../Colab Notebooks"]


def find(source, sub, name):
    cands = []
    if name.endswith(".ipynb"):
        for d in EXTRA_NOTEBOOK_DIRS:
            cands.append(os.path.join(source, d, name) if d else os.path.join(source, name))
        cands.append(os.path.join(os.path.dirname(source.rstrip("/")),
                                 "Colab Notebooks", name))
    else:
        cands.append(os.path.join(source, sub, name))
        cands.append(os.path.join(source, name))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="the working folder, e.g. ~/peltzman")
    ap.add_argument("--dest", default=".", help="the package root")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--optional", action="store_true",
                    help="also copy the items marked optional")
    args = ap.parse_args()

    source = os.path.expanduser(args.source)
    if not os.path.isdir(source):
        sys.exit(f"no such folder: {source}")

    copied, absent_req, absent_opt, skipped, present = [], [], [], [], []
    for row in INVENTORY:
        sub, name, dest_sub, writer, supports, required = row[:6]
        dest_name = row[6] if len(row) > 6 else name
        if not required and not args.optional:
            skipped.append(name)
            continue
        if os.path.isfile(os.path.join(args.dest, dest_sub, dest_name)):
            present.append(os.path.join(dest_sub, dest_name))
            continue
        src = find(source, sub, name)
        if src is None:
            (absent_req if required else absent_opt).append((name, writer, supports))
            continue
        dst = os.path.join(args.dest, dest_sub, dest_name)
        if not args.dry_run:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        copied.append((os.path.join(dest_sub, dest_name), os.path.getsize(src)))

    verb = "would copy" if args.dry_run else "copied"
    print(f"{verb} {len(copied)} file(s)")
    for rel, n in copied:
        print(f"  {rel:<58} {n:>12,} bytes")

    if present:
        print(f"\n{len(present)} file(s) already in the package, left alone:")
        for rel in present:
            print(f"  {rel}")

    if skipped:
        print(f"\n{len(skipped)} optional item(s) not attempted; "
              "rerun with --optional to include them")

    if absent_opt:
        print(f"\n{len(absent_opt)} optional item(s) not found:")
        for name, writer, supports in absent_opt:
            print(f"  {name:<46} {writer}")

    if absent_req:
        print(f"\nMISSING, and the package is incomplete without them "
              f"({len(absent_req)}):\n")
        for name, writer, supports in absent_req:
            print(f"  {name}")
            print(f"      written by  {writer}")
            print(f"      supports    {supports}")
        print("\nIf a file is genuinely gone, rerun the notebook that writes it.")
        return 1

    print("\nEverything required was found.")
    print("Next: python scripts/check_anonymity.py . --names <surname> <username>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
