"""
Peltzman Protocol - durable, resumable job state.

Guarantee
---------
Kill the process, lose the runtime, close the browser, at ANY instant:
  * no file is ever left half-written,
  * no completed work is ever lost,
  * no work is ever silently duplicated,
  * restarting the cell resumes from the last completed batch.

How
---
The key list is fixed and ordered at job creation, and batch `i` is defined as
a deterministic slice of it. A batch's output is therefore a pure function of
its index, so re-running a batch overwrites its own file and can never
duplicate rows. Completion is represented by the *existence* of that file and
nothing else - there is no separate done-list that can drift out of sync with
the data.

Every file is written to a temporary name, flushed, fsync'd, and then moved
into place with os.replace(), which is atomic. A crash mid-write leaves a
stray .tmp file (harmless, cleaned on next run) and the previous state intact.

Because completion is file existence, the crash window is exactly one batch.
Size batches so one takes a few minutes.
"""
from __future__ import annotations
import json, os, time, hashlib, tempfile, shutil, glob, sys
from pathlib import Path

__all__ = ["Job", "atomic_write_text", "atomic_write_bytes"]


# --------------------------------------------------------------- atomic io --
def atomic_write_bytes(path, data: bytes):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())          # no-op on some mounts; harmless
        os.replace(tmp, path)             # atomic within a filesystem
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise


def atomic_write_text(path, text: str):
    atomic_write_bytes(path, text.encode("utf-8"))


def _hash_params(params) -> str:
    blob = json.dumps(params, sort_keys=True, default=str).encode()
    return hashlib.sha1(blob).hexdigest()[:10]


# --------------------------------------------------------------------- job --
class Job:
    """A resumable pass over an ordered list of keys.

    >>> job = Job("nb1_workflows", keys=repos, root=DRIVE, batch_size=25,
    ...           params={"detector": "v3"})
    >>> for i, keys in job.pending():
    ...     job.commit(i, [row for k in keys for row in scan(k)])
    >>> df = job.frame()

    Changing `params` starts a new, separate run directory: results computed
    under different settings are never silently mixed.
    """

    def __init__(self, name, keys, root, batch_size=25, params=None, verbose=True):
        self.name = name
        self.params = dict(params or {})
        self.batch_size = int(batch_size)
        self.verbose = verbose
        # NOTE: the key count is deliberately NOT part of the run identity.
        # If the input list changes at all we want a loud error, not a silent
        # fresh run that looks like "nothing was ever done".
        self.dir = Path(root) / name / _hash_params(
            {"params": self.params, "batch_size": self.batch_size})
        self.shards = self.dir / "shards"
        self.shards.mkdir(parents=True, exist_ok=True)

        keyfile = self.dir / "keys.json"
        if keyfile.exists():
            stored = json.loads(keyfile.read_text())
            if stored != list(keys):
                raise ValueError(
                    f"{self.name}: key list changed since this run started "
                    f"({len(stored)} -> {len(keys)}). Change `params` to start "
                    f"a new run, or restore the original list.")
        else:
            atomic_write_text(keyfile, json.dumps(list(keys)))
            atomic_write_text(self.dir / "meta.json", json.dumps({
                "name": name, "created": time.time(), "n_keys": len(keys),
                "batch_size": self.batch_size, "params": self.params,
                "python": sys.version.split()[0]}, indent=1))

        self.keys = list(keys)
        self._sweep_tmp()
        if verbose:
            d, n = self.n_done_batches(), self.n_batches()
            print(f"[{name}] {self.dir}")
            print(f"[{name}] {d}/{n} batches complete"
                  + (f" — resuming at batch {d}" if 0 < d < n else
                     " — nothing to do" if d == n else " — starting fresh"))

    # ---------------------------------------------------------- internals --
    def _sweep_tmp(self):
        """Remove leftovers from a crash mid-write. They are never valid."""
        for t in glob.glob(str(self.shards / "*.tmp")) + glob.glob(str(self.dir / "*.tmp")):
            try: os.unlink(t)
            except OSError: pass

    def _path(self, i) -> Path:
        return self.shards / f"batch-{i:06d}.jsonl"

    def n_batches(self) -> int:
        return (len(self.keys) + self.batch_size - 1) // self.batch_size

    def batch_keys(self, i):
        return self.keys[i * self.batch_size:(i + 1) * self.batch_size]

    def done_batches(self):
        return {i for i in range(self.n_batches()) if self._path(i).exists()}

    def n_done_batches(self) -> int:
        return len(self.done_batches())

    # ------------------------------------------------------------- driving --
    def pending(self):
        """Yield (batch_index, keys) for every batch not yet committed."""
        done = self.done_batches()
        for i in range(self.n_batches()):
            if i not in done:
                yield i, self.batch_keys(i)

    def commit(self, i, rows):
        """Atomically record this batch's output. Idempotent by construction."""
        payload = "".join(json.dumps(r, separators=(",", ":"), default=str) + "\n"
                          for r in rows)
        atomic_write_text(self._path(i), payload)
        self.beat(i, len(rows))

    def beat(self, i, n_rows=None, note=None):
        atomic_write_text(self.dir / "heartbeat.json", json.dumps({
            "at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "last_batch": i, "rows": n_rows, "note": note,
            "done": self.n_done_batches(), "total": self.n_batches()}, indent=1))

    def run(self, fn, on_error="record", progress_every=1, after_batch=None):
        """Drive the whole job. `fn(key) -> list[dict]`.

        on_error='record'  capture the failure as a row and move on (default)
                 'skip'    drop the key silently
                 'raise'   stop, keeping every committed batch
        after_batch(job, i)  optional hook run after each successful commit,
                 e.g. to replicate state off the runtime. A failing hook never
                 loses the batch - it is already on disk before the hook runs.
        """
        t0, n_before = time.time(), self.n_done_batches()
        for i, keys in self.pending():
            rows = []
            for k in keys:
                try:
                    rows.extend(fn(k) or [])
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    if on_error == "raise":
                        raise
                    if on_error == "record":
                        rows.append({"_key": k, "_error": f"{type(e).__name__}: {e}"})
            self.commit(i, rows)
            if after_batch is not None:
                try: after_batch(self, i)
                except Exception as e:
                    print(f"  after_batch hook failed ({type(e).__name__}: {e}) — "
                          f"batch is still committed locally")
            done = self.n_done_batches()
            if self.verbose and (done - n_before) % progress_every == 0:
                el = time.time() - t0
                per = el / max(1, done - n_before)
                left = (self.n_batches() - done) * per
                print(f"  batch {done}/{self.n_batches()}  "
                      f"{per:5.1f}s/batch  ~{left/60:5.1f} min remaining")
        if self.verbose:
            print(f"[{self.name}] complete: {self.n_batches()} batches")

    # ------------------------------------------------------------ reading --
    def rows(self, drop_errors=True):
        """Iterate every committed row. Truncated trailing lines - which an
        atomic write cannot produce, but a copied/synced file might - are
        skipped and counted rather than raising."""
        bad = 0
        for i in sorted(self.done_batches()):
            with open(self._path(i), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        bad += 1
                        continue
                    if drop_errors and isinstance(r, dict) and "_error" in r:
                        continue
                    yield r
        if bad and self.verbose:
            print(f"[{self.name}] warning: skipped {bad} unparseable line(s) — "
                  f"run .verify() to locate")

    def frame(self, drop_errors=True):
        import pandas as pd
        return pd.DataFrame(list(self.rows(drop_errors=drop_errors)))

    def errors(self):
        return [r for r in self.rows(drop_errors=False)
                if isinstance(r, dict) and "_error" in r]

    # -------------------------------------------------------- maintenance --
    def verify(self):
        """Check every committed shard parses. Returns list of bad batch ids."""
        bad = []
        for i in sorted(self.done_batches()):
            try:
                for line in open(self._path(i), encoding="utf-8"):
                    if line.strip():
                        json.loads(line)
            except Exception as e:
                bad.append((i, f"{type(e).__name__}: {e}"))
        if self.verbose:
            print(f"[{self.name}] verify: {self.n_done_batches()} shards, "
                  f"{len(bad)} damaged")
        return bad

    def reset(self, batches=None):
        """Delete shards so they are recomputed. `batches=None` resets damaged
        ones only; pass an iterable of indices, or 'all'."""
        if batches == "all":
            targets = sorted(self.done_batches())
        elif batches is None:
            targets = [i for i, _ in self.verify()]
        else:
            targets = list(batches)
        for i in targets:
            try: os.unlink(self._path(i))
            except OSError: pass
        if self.verbose:
            print(f"[{self.name}] reset {len(targets)} batch(es)")
        return targets

    def retry_errors(self):
        """Re-queue every batch that recorded at least one failure."""
        hit = set()
        for i in sorted(self.done_batches()):
            for line in open(self._path(i), encoding="utf-8"):
                if '"_error"' in line:
                    hit.add(i); break
        return self.reset(hit)

    def export(self, path, fmt="parquet"):
        """Write the whole result set as one file, atomically."""
        df = self.frame()
        p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        if fmt == "parquet":
            df.to_parquet(tmp, index=False)
        else:
            df.to_csv(tmp, index=False)
        os.replace(tmp, p)
        if self.verbose:
            print(f"[{self.name}] exported {len(df):,} rows -> {p}")
        return p

    def status(self):
        hb = self.dir / "heartbeat.json"
        return {"dir": str(self.dir), "batches": self.n_batches(),
                "done": self.n_done_batches(), "keys": len(self.keys),
                "heartbeat": json.loads(hb.read_text()) if hb.exists() else None}
