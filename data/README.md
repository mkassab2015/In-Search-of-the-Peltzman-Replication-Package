# data/

No public corpus is redistributed here. `docs/PROVENANCE.md` records which
source each pipeline stage reads.

- **Workflow file histories.** Cardoen, Mens and Decan, *A dataset of GitHub
  Actions workflow histories*, Zenodo record 20340547, release 2026-05-22.
  Download it from Zenodo and place it under `data/raw/`. NB1 extracts it.
- **The GitHub event stream.** Read by NB3 and NB3b from ClickHouse's public
  GitHub mirror, table `github.events`, over HTTPS as the `demo` user. No
  credential is needed and none is stored here.
- **The repository frame.** Built by NB0 from the GH Archive BigQuery export
  (`githubarchive.day.*`, `githubarchive.month.*`) and the GitHub REST search
  API. Running it needs a BigQuery project and a GitHub token of your own.
- **Repository clones.** NB0b and NB2 clone candidate repositories over HTTPS
  and read the workflow history from the local clone. The clones are
  disposable and are not retained.

## data/derived/

Parquets the pipeline builds from those sources.

| File | Rows | Written by |
|---|---|---|
| `nb1_treatments.parquet` | first adoption per repository | NB1 |
| `nb2_config_treatments.parquet` | Treatment B and control arms | NB2 |
| `nb4_panel_balanced.parquet` | 1,678,508 repository-months | NB4 |

The balanced panel is the input to every estimate in Tables IV, V and VI. It
holds 44 columns: the repository, the month index, the eight outcomes, five
logged counts, and a cohort, event-time and post indicator for each of the
nine treatment arms. Never-treated repositories carry the sentinel cohort
`1e9` in `g_A`. Verified on this copy: 1,678,508 rows over 27,554
repositories and 72 months, 14,019 treated against 13,535 never-treated in 71
adoption cohorts, matching Table I.

## The validation instrument

Both copies of the workbook are here.

`detector_validation_blank.xlsx` is the instrument as it went to the labeller:
175 sampled workflow files with their repository of origin, the question asked
of each, the written labeling rule, the stratum design, and an empty LABEL
column. It documents the protocol.

`detector_validation_labelled.xlsx` is the same workbook with the labels
applied: 89 yes, 80 no and 6 unclear over the 175 rows, with the worked
example untouched. With `../state/nb7_validation_key.json`, which holds the
classifier verdicts that were kept out of the workbook so the labeling stayed
blind, `scripts/score_validation.py` regenerates Table II in full.

The workflow text both quote is public file content from the repositories
named in the sheet.
