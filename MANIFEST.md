# Manifest

Status of every path the paper's Data Availability statement promises.

| Promised | Status |
|---|---|
| Derived panels | present, `data/derived/`, including the 1,678,508-row estimation panel |
| Detector definitions | present, `src/detectors.py`, with `tests/test_detectors.py` |
| Analysis code for every estimate and check | present, `notebooks/`, `src/`, `scripts/` |
| Machine-readable outputs | present for Tables II to VI and Figures 2 and 3, plus nine per-stage summaries |
| Manual validation labels and answer key | present, `data/detector_validation_labelled.xlsx` and `state/nb7_validation_key.json` |
| Claim-to-file map | present, `docs/CLAIMS.md` |

Every row is satisfied. `MISSING.md` records one robustness run that did not
complete and the pipeline files not carried; no reported number depends on
either.

## Contents (78 files, 77 listed)

| Path | Bytes | SHA-256 (16) | Role |
|---|---|---|---|
| `.gitignore` | 327 | `e1f54509a94509c3` |  |
| `CITATION.cff` | 355 | `63794e64ef306520` |  |
| `LICENSE` | 1068 | `9f1abe28a25b5f6f` |  |
| `MISSING.md` | 2319 | `6a62d02791b380b0` |  |
| `README.md` | 5888 | `67466af706b8f20c` | start here |
| `data/README.md` | 2561 | `baf2b4c00f76aef0` | what each source is and where to get it |
| `data/derived/nb1_treatments.parquet` | 428384 | `4a6af524a0feabd3` | first adoption per repository |
| `data/derived/nb2_config_treatments.parquet` | 24369 | `09c5cf63aaf52687` | Treatment B and control arms |
| `data/derived/nb4_panel_balanced.parquet` | 19061795 | `0142ee22362c39f2` | the estimation panel, 1,678,508 repository-months |
| `data/detector_validation_blank.xlsx` | 135789 | `b5c49bb252027791` | validation instrument, 175 rows, LABEL column empty |
| `data/detector_validation_labelled.xlsx` | 136576 | `f2c3ddd9be302d01` | the hand labels: 89 yes, 80 no, 6 unclear over 175 rows |
| `docs/CLAIMS.md` | 8445 | `6852bbfb358bde36` | every reported number and its producing file |
| `docs/LEDGER.md` | 2961 | `f3fa8f2f207ff437` | what each stage was run with, and the two seeds |
| `docs/PROVENANCE.md` | 2158 | `2ef6dcec20e3ff8b` | which source each stage reads |
| `figures/README.md` | 339 | `bb9b0c7a291da27e` | what make_figures.py writes and what it needs |
| `notebooks/NB0_gate.ipynb` | 79802 | `c9973ceca009fc4d` | repository frame, cost estimate, BigQuery and REST |
| `notebooks/NB0b_bundling.ipynb` | 56189 | `bddcae2bd50716ca` | bundling rate, Section IV; clones repositories |
| `notebooks/NB1_treatments.ipynb` | 58827 | `752728cfba8750df` | workflow file histories from Zenodo 20340547 |
| `notebooks/NB2_configs.ipynb` | 51774 | `43b6e00460ab7ae2` | detector pass over file versions, Treatments A and B |
| `notebooks/NB3_panel.ipynb` | 39381 | `8def13e13bb8f294` | monthly outcomes from the event mirror |
| `notebooks/NB3b_panel_human.ipynb` | 37376 | `9c5dd50db9350823` | the same outcomes with bot activity removed |
| `notebooks/NB4_panel_power.ipynb` | 42245 | `794e1aa4a63acbae` | panel assembly, randomization inference, MDE |
| `notebooks/NB5_estimation.ipynb` | 49875 | `9cd85dbe48ec0ec8` | group-time ATT, Table IV, Figure 2 |
| `notebooks/NB6_bots_and_eventstudies.ipynb` | 48003 | `9277ac1ed954cbb5` | Treatment B arms, Table V, bot comparison |
| `notebooks/NB7_detector_validation.ipynb` | 46339 | `c1bd13dd8a80c066` | validation sampling and scoring, Table II |
| `notebooks/NB8_robustness.ipynb` | 44434 | `432776fe12d28426` | the four checks, Table VI Panels A to D |
| `requirements.txt` | 373 | `69cd8310cc33691a` | pinned versions |
| `results/README.md` | 4811 | `9589125fa756c632` | what each output file holds |
| `results/detector_validation_scored.csv` | 665 | `332b11b32041dba5` | per-detector precision and recall |
| `results/detector_validation_scored.json` | 3027 | `135c338c42b89f90` | Table II in full, with both agreement rows and their kappas |
| `results/event_study.csv` | 2568 | `1cd7e1bcf0915a05` | Figure 2 |
| `results/gateC.json` | 45 | `92ac0c7579500d3b` | bundling pilot, 56 of 80 |
| `results/nb1_summary.json` | 387 | `804591c7418dc3f3` | 3,734,686 file versions, 20,155 eligible, bundling 0.717 |
| `results/nb2_summary.json` | 450 | `198030e0b4d15996` | the 3,000-repository config sample |
| `results/nb3_summary.json` | 466 | `282986597fb540c3` | outcome totals, Table III |
| `results/nb3b_summary.json` | 764 | `14975d967b62dd12` | bot shares per outcome |
| `results/nb4_mde.csv` | 10945 | `56b45e3c525d343b` | minimum detectable effect and randomization center, Section V-B |
| `results/nb4_summary.json` | 640 | `006dc9e5cab41942` | panel size, inactive share, the MDE |
| `results/nb5_summary.json` | 1776 | `3c9aaf0976099990` | Treatment A estimates and the pre-trend test |
| `results/nb6_summary.json` | 1698 | `c67b5fc80c453185` | bot contrast, 2 sign flips |
| `results/nb8_armb3_path_o5_self_merge_rate.csv` | 4535 | `24396edee6d02913` | Figure 3, placebo and real event paths |
| `results/nb8_marginal_placebo.csv` | 1476 | `40776769b7eaf0a2` | Check 3, the reported placebo estimate |
| `results/nb8_r1a_placebo_precommit.csv` | 619 | `12fe2626c1f5a1a4` | Check 3, pre-commit arm, no usable cells |
| `results/nb8_r1b_placebo_nongating.csv` | 506 | `b41e14e28015ad24` | Check 3, non-gating arm, no controls, no usable cells |
| `results/nb8_r1b_placebo_nyt.csv` | 959 | `739f476181d3ac6b` | Check 3, not-yet-treated comparison, Panel C |
| `results/nb8_r2_pretrends.csv` | 1855 | `f97d4649fab77d60` | Check 4, Panel D, five pre-trend tests |
| `results/nb8_r3_era.csv` | 2788 | `6f050e56f1483b28` | Check 4, per-era ATTs behind the difference |
| `results/nb8_r3_era_diff.csv` | 874 | `91f55c35485a6767` | Check 4, era split at June 2022 |
| `results/nb8_r4_no_month0.csv` | 1419 | `a39cfe19f5b74835` | ATT excluding the adoption month, Section V-C |
| `results/nb8_summary.json` | 16146 | `70b9ee40250cfa9b` | the reconciliation gate, the estimator used, R5 status |
| `results/results_bots.csv` | 2978 | `419e48445606536b` | Table VI Panel B |
| `results/results_main.csv` | 6401 | `edb16acd83e329fb` | Tables IV, V and VI Panel A |
| `results/results_multiplicity.csv` | 1154 | `8c8a349db3052822` | Table IV, BH-adjusted p-values |
| `scripts/build_nb8.py` | 35606 | `7015becdbe1d3dfe` | generates NB8_robustness.ipynb |
| `scripts/check_anonymity.py` | 6943 | `97489211f3aec22a` | pre-deposit scan |
| `scripts/collect_package.py` | 5150 | `a24c734d15f8c454` | pulls files out of a working copy |
| `scripts/collect_paper_data.py` | 10857 | `6a0ad59b772c9fde` | extracts the reported numbers, Tables I to VII |
| `scripts/fetch_remaining.py` | 9873 | `ad57c83772833a81` | copies the 12 required and 22 optional files out of the working folder |
| `scripts/fetch_sources.py` | 5980 | `dcf22e04899832a5` | downloads the public corpora |
| `scripts/make_figures.py` | 11213 | `c070d65b1cd61e8f` | Figures 2 and 3 |
| `scripts/nb8_armb.py` | 6423 | `a5d113c45b137d22` | Check 3, placebo arm |
| `scripts/nb8_armb2.py` | 5311 | `a46d05c7b2dd7806` | Check 3, Panel C |
| `scripts/nb8_armb3.py` | 4834 | `39840d8ace6ab7e2` | Check 3, event paths, Figure 3 input |
| `scripts/nb8_armb4.py` | 7770 | `4b27bbdf7a62b138` | Check 3, matched marginal placebo |
| `scripts/nb8_placebo_standalone.py` | 9623 | `d2505c485588130e` | Check 3, matched marginal placebo, standalone |
| `scripts/score_validation.py` | 8588 | `34556f6a9cf82af7` | Table II from the labels and the key |
| `src/cs_did.py` | 7432 | `75f012075d353123` | Callaway-Sant'Anna group-time ATT, multiplier bootstrap, sup-t |
| `src/detectors.py` | 6588 | `8087eed06a2308ab` | the five detectors, triggers, first adoption, bundling |
| `src/panel_tools.py` | 5425 | `856b825f236ef84f` | month index, two-way demeaning, TWFE, event study, MDE |
| `src/peltzman_io.py` | 11912 | `cd215c822b483e64` | resumable job state, atomic writes |
| `state/README.md` | 769 | `d1fc6906f6166ef7` | how job state works |
| `state/nb1_controls.json` | 624272 | `2a0f4e98cc5ecab3` | the never-treated control set |
| `state/nb1_first_seen.json` | 1994924 | `c4b693df452fc7be` | first-seen month per repository |
| `state/nb7_sample.json` | 1153956 | `1f35680feb99bec9` | the full validation sampling record, 175 files |
| `state/nb7_validation_key.json` | 25162 | `bbc5b730fd1a2520` | Table II, the held-out classifier verdicts |
| `tests/test_detectors.py` | 3816 | `73ee6fad65bd6729` | 24 checks, including the YAML `on:` trap |
| `tests/test_peltzman_io.py` | 5605 | `4861a7d90e849851` | 7 crash scenarios, 28 assertions |

Hashes are the first 16 hex characters of the SHA-256 of the file as
deposited. Recompute them on the extracted archive to confirm the transfer.
`MANIFEST.md` is not listed above, since it cannot carry its own hash.
