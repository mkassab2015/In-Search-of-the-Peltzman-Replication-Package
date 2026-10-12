# Run ledger

What each stage was run with. Dates and wall-clock times come from your own
run records and are the one column this package cannot fill for you.

| Stage | Seed | Window | Other settings | Reads | Writes |
|---|---|---|---|---|---|
| NB0_gate | — | 2019-07 .. 2025-06 | `MIN_STARS=100`, `BUNDLE_MONTHS=3`, cost month 2026-06, event day 2026-06-10 | GH Archive BigQuery, GitHub REST | repository frame |
| NB1_treatments | — | 2019-07 .. 2025-06 | Zenodo record 20340547, `MIN_AGE_MONTHS=12`, `MARGINAL_GAP=3`, `N_BUCKETS=64` | Zenodo corpus | extracted workflow file versions |
| NB2_configs | 20261005 | 2019-07 .. 2025-06 | `N_TREATED=1500`, `N_CONTROL=1500`, `MIN_AGE_MONTHS=12` | NB1 output | Treatments A and B, cohorts |
| NB3_panel | 20261005 | 2019-07 .. 2025-06 | `REPOS_PER_Q=6000`, `RETRIES=4` | ClickHouse `github.events` | monthly outcomes |
| NB3b_panel_human | 20261005 | 2019-07 .. 2025-06 | as NB3, bot activity removed | ClickHouse `github.events` | human-only outcomes |
| NB4_panel_power | 20261005 | 2019-07 .. 2025-06 | randomization inference, MDE = 2.802 x SE | NB2, NB3, NB3b | `data/derived/panel.parquet` |
| NB5_estimation | 20261005 | 2019-07 .. 2025-06 | `N_BOOT=500`, `MIN_CELL=10`, `MAX_LEAD=12`, `MAX_LAG=24` | derived panel | `results/results_main.csv`, `results/results_multiplicity.csv`, `results/event_study.csv` |
| NB6_bots_and_eventstudies | 20261005 | 2019-07 .. 2025-06 | as NB5 | derived panel | Treatment B rows, `results/results_bots.csv` |
| NB7_detector_validation | 20261005 | — | 175 rows, three strata, 4000-character display cap | NB2 output | validation instrument, held-out key |
| NB0b_bundling | - | 2019-07 .. 2025-06 | 200 repositories created before 2019-01-01, cloned over HTTPS | git clones | bundling rate, Section IV |
| NB8_robustness | 20260101 | 2019-07 .. 2025-06 | `N_BOOT=500`, `MIN_CELL=10`, `MAX_LEAD=12`, `MAX_LAG=24`, estimator `cs_did.py` | derived panel | Table VI, runs R1 to R4; R5 blocked |
| nb8_armb2, nb8_armb3, nb8_armb4, nb8_placebo_standalone | 20260101 | 2019-07 .. 2025-06 | as NB8 | derived panel | Check 3 outputs |

## On the two seeds

The pipeline that produces the reported estimates uses `SEED = 20261005`. The
Section VI robustness checks use `SEED = 20260101`. The seed governs the
multiplier-bootstrap draws and the sampling in NB2 and NB7; it is held fixed
within each of the two groups, which is what the comparisons in Table VI
require. The two groups differ because the checks were written later.

One thing to settle before depositing: Table VI Panel A reports TWFE against
Callaway-Sant'Anna for the eight outcomes, and both columns exist in two
places, `results/results_main.csv` from the main pipeline and NB8's own
recomputation. Confirm which set was typeset and say so here. The two agree
to within 0.7-8.3% on standard errors and 0.53 SE on point estimates, so the
Panel A conclusion does not turn on it, but a replicator will check.
