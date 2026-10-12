# state/

Durable job state for the long-running ingestion and estimation jobs.

Jobs are resumable: work is split into deterministic batch slices, each slice
is written with `os.replace` so a partial file is never visible, and
completion is defined as the output file existing. Re-running a finished job
is a no-op. `src/peltzman_io.py` implements this and
`tests/test_peltzman_io.py` verifies it against SIGKILL mid-batch, SIGKILL
mid-write, re-run after partial completion, a corrupted shard and changed
inputs under a running job.

The run-local shards are not redistributed. One file that belongs here is
listed in `../MISSING.md`: `nb7_validation_key.json`, the held-out classifier
verdicts that `scripts/score_validation.py` joins to the labels at scoring
time.
