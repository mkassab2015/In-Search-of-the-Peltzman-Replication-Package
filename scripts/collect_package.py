#!/usr/bin/env python3
"""Collect the replication package from your working copy.

Most of what this package needs is not missing from the world: it is in the
project folder you ran the analysis from. This walks that folder, copies the
files it recognises into the package layout, and reports what is still absent.

Usage, in Colab:
    from google.colab import drive; drive.mount('/content/drive')
    !python scripts/collect_package.py \
        --source /content/drive/MyDrive/peltzman --dest .

Usage, locally:
    python scripts/collect_package.py --source ~/peltzman --dest .

Nothing is moved or deleted; every file is copied.
"""
import argparse
import fnmatch
import os
import shutil
import sys

# (destination subdir, glob patterns). First match wins.
RULES = [
    ("notebooks", ["NB*.ipynb", "*_nb*.ipynb"]),
    ("src",       ["peltzman_io.py", "detectors.py", "panel_tools.py",
                   "cs_did.py", "test_*.py", "src/*.py"]),
    ("scripts",   ["make_figures*.py", "collect_paper_data.py",
                   "score_validation.py", "nb8_*.py", "build_nb8.py",
                   "scripts/*.py"]),
    ("results",   ["event_study.csv", "results_multiplicity.csv",
                   "nb8_*path*.csv", "results/*.csv", "*_results.csv"]),
    ("data",      ["validation*.csv", "answer_key*.csv", "*labels*.csv"]),
    ("docs",      ["LEDGER.md", "docs/*.md"]),
    ("figures",   ["fig*.pdf", "fig*.png", "fig*.jpg"]),
]

# What the paper's Data Availability statement promises.
REQUIRED = {
    "src/detectors.py":                 "the detector definitions",
    "src/cs_did.py":                    "the group-time estimator",
    "src/peltzman_io.py":               "IO helpers",
    "src/panel_tools.py":               "panel construction",
    "scripts/score_validation.py":      "Table II",
    "results/event_study.csv":          "Figure 2, event-study values",
    "results/results_multiplicity.csv": "Table IV, BH-adjusted p-values",
    "data/validation_sample.csv":       "the 175 hand-labelled files",
    "data/validation_answer_key.csv":   "the answer key",
    "docs/LEDGER.md":                   "the run ledger",
}

SKIP_DIRS = {".git", "__pycache__", ".ipynb_checkpoints", "raw", "derived",
             "state", "node_modules"}
SKIP_EXT = {".parquet", ".gz", ".zip", ".pyc"}


def classify(relpath):
    base = os.path.basename(relpath)
    for dest, patterns in RULES:
        for pat in patterns:
            target = relpath if "/" in pat else base
            if fnmatch.fnmatch(target, pat):
                return dest
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="your project folder")
    ap.add_argument("--dest", default=".", help="package root")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = os.path.abspath(os.path.expanduser(args.source))
    dst = os.path.abspath(os.path.expanduser(args.dest))
    if not os.path.isdir(src):
        print(f"source not found: {src}")
        return 2

    copied, skipped, unrecognised = [], [], []

    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, src)
            if os.path.splitext(fn)[1].lower() in SKIP_EXT:
                skipped.append((rel, "large or compressed, see data/README.md"))
                continue
            sub = classify(rel)
            if sub is None:
                unrecognised.append(rel)
                continue
            out = os.path.join(dst, sub, os.path.basename(rel))
            if os.path.exists(out):
                skipped.append((rel, "already in package"))
                continue
            if not args.dry_run:
                os.makedirs(os.path.dirname(out), exist_ok=True)
                shutil.copy2(full, out)
            copied.append((rel, os.path.relpath(out, dst)))

    print(f"copied {len(copied)} file(s)" + (" (dry run)" if args.dry_run else ""))
    for rel, out in sorted(copied):
        print(f"  {rel:<44} -> {out}")

    if unrecognised:
        print(f"\nnot recognised, {len(unrecognised)} file(s). Copy by hand "
              f"if any belong in the package:")
        for rel in sorted(unrecognised)[:40]:
            print(f"  {rel}")
        if len(unrecognised) > 40:
            print(f"  ... and {len(unrecognised) - 40} more")

    print("\nagainst what Data Availability promises:")
    absent = 0
    for path, role in REQUIRED.items():
        here = os.path.exists(os.path.join(dst, path))
        if not here:
            absent += 1
        print(f"  [{'x' if here else ' '}] {path:<36} {role}")

    if absent:
        print(f"\n{absent} required item(s) still absent. The derived panel is "
              f"separate again: see data/README.md.")
    else:
        print("\nall required items present.")

    print("\nnext: python scripts/check_anonymity.py . --names <surname> <username>")
    return 1 if absent else 0


if __name__ == "__main__":
    sys.exit(main())
