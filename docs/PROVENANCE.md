# Which source each stage reads

Recorded from the notebooks themselves, because the paper's data section
names two sources and the pipeline reads four.

| Stage | Source it queries | Access path |
|---|---|---|
| NB0, repository frame and cost estimate | GH Archive, BigQuery export: `githubarchive.day.*`, `githubarchive.month.*` | `google-cloud-bigquery` |
| NB0, star and activity filters on candidate repositories | GitHub REST API: `/search/repositories`, `/rate_limit` | token from the notebook secret store |
| NB1, workflow file versions | Zenodo record 20340547, release 2026-05-22 | HTTPS download, extracted locally |
| NB2, detector pass | the extracted corpus from NB1 | local |
| NB3, NB3b, monthly outcomes | ClickHouse public GitHub mirror, table `github.events`, host `sql-clickhouse.clickhouse.com`, user `demo` | HTTPS, read-only public endpoint |
| NB4 to NB8 | the derived panel | local |

Two consequences worth stating in the paper.

The event stream is read through ClickHouse's public mirror of GitHub events,
not from GH Archive's hourly files. The mirror is built from the same event
stream, but it is a third party's ingestion of it, and a replicator pointed at
the hourly files could get a different row count for any month where the two
ingestions differ. The paper's data section should name the mirror.

The frame is drawn partly through the GitHub search API, whose ranking and
result cap are not guaranteed stable over time. A replicator running NB0
later will get a frame close to, but not identical to, ours. The frame we used
is fixed in the derived panel.

No credential is stored anywhere in this package. Tokens are read from the
notebook secret store at run time.

## Two stages clone repositories directly

`NB0b_bundling.ipynb` and `NB2_configs.ipynb` clone candidate repositories
over HTTPS (`CLONE_TIMEOUT`, `MAX_REPO_MB` bound the work) and read the
workflow file history out of the local clone, rather than reading it from the
Zenodo corpus. That is a fifth access path and a fifth thing a replicator
needs: network egress to github.com and disk for the clones. The clones are
disposable and are not retained.
