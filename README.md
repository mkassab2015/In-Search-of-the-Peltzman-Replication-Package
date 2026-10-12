# In Search of the Peltzman Effect in Code Review

Replication package for the MSR 2027 submission. Anonymized for
double-anonymous review.

The package holds the full pipeline: the repository frame, the detectors and
their unit tests, the panel construction, the group-time ATT estimator, the
Treatment B arms, the detector-validation instrument, the four robustness
checks of Section VI, and the machine-readable outputs behind Tables IV, V
and VI and Figure 2. Every number reported in the paper traces to a file here, and
[`docs/CLAIMS.md`](docs/CLAIMS.md) is the map. [`MISSING.md`](MISSING.md)
records the one robustness run that did not complete and the files the
pipeline wrote that are not carried, none of which supports a reported
number.

## What the paper does

We estimate the effect of a repository's first pre-merge check on eight
monthly code-review outcomes across 27,554 GitHub repositories and 1,678,508
repository-months, using group-time average treatment effects against
never-treated controls. We then reverse four analysis decisions one at a
time, holding sample, cohorts, outcomes and inference fixed: the estimator,
the counting of bot-authored activity, the attribution of the effect to the
check rather than to the workflow carrying it, and the coverage of the
parallel-trends test.

## Layout

    notebooks/   NB0 frame, NB0b bundling, NB1 workflow histories,
                 NB2 detector pass,
                 NB3/NB3b outcomes, NB4 panel and power, NB5 estimation,
                 NB6 Treatment B and event studies, NB7 validation,
                 NB8 the four robustness checks
    src/         detectors, panel helpers, the Callaway-Sant'Anna
                 implementation, resumable job IO
    tests/       unit tests for the detectors and the job IO
    scripts/     placebo variants, figure generation, validation scoring,
                 paper-number extraction, the remaining-files fetch,
                 anonymity check
    data/        the estimation panel, the upstream parquets, and the
                 validation workbook; no public corpus is redistributed
    results/     machine-readable outputs, one per reported number;
                 results/README.md says what each holds
    state/       resumable job bookkeeping
    docs/        CLAIMS.md maps every claim to its producing file;
                 PROVENANCE.md records which source each stage reads
    figures/     output of scripts/make_figures.py; empty in this copy

## A note on where the modules live

The pipeline was developed in Colab, where the shared modules were written
to disk by `%%writefile` cells at the top of each notebook rather than kept
as separate files. `src/` and `tests/` here are those cells extracted
verbatim, so the notebooks and `src/` hold the same code twice. Running a
notebook rewrites its own copy under `/content`. The only edit made during
extraction was to the two test files, whose `sys.path` line pointed at the
Colab path; they now resolve `src/` relative to their own location.

## Reproducing

    pip install -r requirements.txt
    python tests/test_detectors.py        # 24 checks
    python tests/test_peltzman_io.py      # 7 scenarios, 28 assertions
    python scripts/score_validation.py \
        data/detector_validation_labelled.xlsx state/nb7_validation_key.json

The two test suites run against nothing but the extracted modules and pass
without any data. The third regenerates Table II from the hand labels and the
held-out key in a second. Everything downstream needs the corpora in
[`data/README.md`](data/README.md) or the derived panel.

The derived panel is under `data/derived/`, so these run as they are:

    jupyter execute notebooks/NB5_estimation.ipynb      # Table IV, Figure 2
    jupyter execute notebooks/NB6_bots_and_eventstudies.ipynb   # Table V
    jupyter execute notebooks/NB8_robustness.ipynb      # Table VI, Panels A-D
    python scripts/nb8_armb2.py                         # Check 3, Panel C
    python scripts/nb8_armb3.py                         # Figure 3 input
    python scripts/make_figures.py                      # Figures 2 and 3

From the public corpora, in order: NB0, NB1, NB2, NB3, NB3b, NB4.

## Settings

    N_BOOT = 500   MIN_CELL = 10   MAX_LEAD = 12   MAX_LAG = 24
    WINDOW = 2019-07 .. 2025-06

Held fixed across the four checks of Section VI, which is what the
comparisons there require. The main pipeline runs under `SEED = 20261005` and
the Section VI checks under `SEED = 20260101`; `docs/LEDGER.md` records which
stage uses which and why.

Jobs are resumable. Work is split into deterministic batch slices, each slice
is written with `os.replace` so a partial file is never visible, and
completion is defined as the output file existing.

## Two implementation notes

YAML 1.1 resolves the unquoted key `on` to the boolean `True`, so a parser
looking up the string key finds no triggers and classifies every workflow as
non-triggering. `src/detectors.py` handles this and
`tests/test_detectors.py` pins the behavior; a naive reimplementation will
get every classification wrong in the same direction.

`src/cs_did.py` rejects the sum-of-squared-z pre-trend test in favor of a
simultaneous sup-t band from the multiplier bootstrap, and says why in a
comment at the function. The two tests disagree on this data.

## Before depositing

    python scripts/check_anonymity.py . --names <surname> <username>

The script reads file contents and the XML parts of Office files, including
their author metadata. It cannot see your uploader name, ORCID, archive owner
fields or image EXIF; check those by hand.

## Data sources

None is redistributed. See [`data/README.md`](data/README.md) and
[`docs/PROVENANCE.md`](docs/PROVENANCE.md).

## License

MIT for the code. The validation instrument is released under the same terms.
The public corpora keep their own licenses.
