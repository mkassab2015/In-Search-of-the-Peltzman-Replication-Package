# What this package does not contain

Nothing the paper depends on. This file records two things a reader comparing
the outputs against the run records would otherwise wonder about, and what is
deliberately left out.

## R5, the gate-removal rate, did not run

`results/nb8_summary.json` records:

    "r5_removal": "blocked: needs nb0_gate_monthly.parquet"

NB0 did not retain that input, so no removal rate was computed and no
`nb8_r5_removal.csv` exists. Nothing in the paper rests on it. Section
VIII-B-a states that the design does not measure how often a pre-merge check
disappears and argues only that removal would attenuate estimates toward
zero. No rate is claimed anywhere.

## Files the pipeline wrote that are not here

`nb0_gate.parquet` and `nb0_gate_monthly.parquet`, NB0's own outputs, the
second of which is what blocked R5. `nb8_r1b_marginal_placebo.csv`, an earlier
run of the arm that `nb8_marginal_placebo.csv` supersedes.
`nb8_armb3_path_o1_reviewers_per_pr.csv` and
`nb8_armb3_path_o3_review_coverage.csv`, which were never produced because
Figure 3 plots the self-merge rate only. `nb7_sample_repos.json`, whose write
produced an empty object. None supports a reported number.

Two upstream panels are also left out for size: `nb3_panel.parquet` (39 MB)
and `nb3_panel_rawbots.parquet` (24 MB). Both are rebuilt by NB3 and NB3b from
the sources in `docs/PROVENANCE.md`, and the balanced panel they feed,
`data/derived/nb4_panel_balanced.parquet`, is here.

## Deliberately not here

The corpora in the working folder's `raw/` directory (`workflows.tar.gz`,
`workflows.csv.gz`, `repositories.csv.gz`) are not redistributed;
`data/README.md` and `docs/PROVENANCE.md` say where to get them. The job
shards (`keys.json`, `meta.json`, `heartbeat.json`, `atomic.json`, and the
per-batch files) are run-local bookkeeping.

## Before you deposit

    python scripts/score_validation.py data/detector_validation_labelled.xlsx \
        state/nb7_validation_key.json
    python scripts/check_anonymity.py . --names <surname> <username>
    python tests/test_detectors.py
    python tests/test_peltzman_io.py

Then check the archive metadata itself. A Zenodo or Figshare deposit carries
uploader details, and a `.git` directory carries commit author names and
emails. Deposit a clean export, not a clone.
