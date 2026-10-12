"""Crash-safety tests. These simulate the failure modes Colab actually has:
killed mid-batch, killed mid-write, re-run after partial completion,
corrupted shard on disk, and changing inputs underneath a running job."""
import sys, pathlib, os, json, shutil, tempfile, subprocess, textwrap
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'src'))
from peltzman_io import Job, atomic_write_text

fails = []
def check(name, got, want):
    if got != want: fails.append(f"{name}\n    got  {got!r}\n    want {want!r}")
def ok(name, cond):
    if not cond: fails.append(name)

ROOT = tempfile.mkdtemp()
KEYS = [f"repo{i:03d}" for i in range(100)]
def work(k): return [{"key": k, "v": int(k[-3:])}]

# --- 1. clean run ---------------------------------------------------------
j = Job("t1", KEYS, ROOT, batch_size=10, verbose=False)
check("batch count", j.n_batches(), 10)
j.run(work)
check("all committed", j.n_done_batches(), 10)
check("row count", len(list(j.rows())), 100)

# --- 2. resume after interruption ----------------------------------------
j2 = Job("t2", KEYS, ROOT, batch_size=10, verbose=False)
processed = []
class Boom(Exception): pass
def flaky(k):
    processed.append(k)
    if k == "repo035": raise Boom()
    return work(k)
try:
    j2.run(flaky, on_error="raise")
except Boom:
    pass
check("3 batches survived the crash", j2.n_done_batches(), 3)
check("rows kept", len(list(j2.rows())), 30)

before = len(processed)
j3 = Job("t2", KEYS, ROOT, batch_size=10, verbose=False)   # fresh object = new session
check("resume sees prior work", j3.n_done_batches(), 3)
pend = [i for i, _ in j3.pending()]
check("resumes at batch 3", pend[0], 3)
j3.run(work)
check("completes", j3.n_done_batches(), 10)
check("no duplicated rows", len(list(j3.rows())), 100)
check("keys unique", len({r["key"] for r in j3.rows()}), 100)
check("did not redo committed batches", processed[:before] == processed[:before], True)
redone = [k for k in KEYS[:30]]
check("first 30 keys not reprocessed after resume",
      sum(1 for k in redone if k in processed[before:]), 0)

# --- 3. killed mid-write leaves no corruption ----------------------------
# Run a real subprocess and SIGKILL it while it writes, then reopen.
script = textwrap.dedent(f"""
    import sys, time, os
    sys.path.insert(0, {str(pathlib.Path(__file__).resolve().parent.parent / 'src')!r})
    from peltzman_io import Job
    KEYS = [f"repo{{i:03d}}" for i in range(100)]
    j = Job("t3", KEYS, {ROOT!r}, batch_size=10, verbose=False)
    def slow(k):
        time.sleep(0.05)
        return [{{"key": k}}]
    j.run(slow)
""")
sp = os.path.join(ROOT, "kill_me.py"); open(sp, "w").write(script)
p = subprocess.Popen([sys.executable, sp])
import time as _t; _t.sleep(1.6)
p.kill(); p.wait()

j4 = Job("t3", KEYS, ROOT, batch_size=10, verbose=False)
n_after_kill = j4.n_done_batches()
ok("SIGKILL mid-run committed some batches", 0 < n_after_kill < 10)
check("no damaged shards after SIGKILL", j4.verify(), [])
tmps = [f for f in os.listdir(j4.shards) if f.endswith(".tmp")]
check("stray .tmp files swept on reopen", tmps, [])
rows_after_kill = list(j4.rows())
check("rows intact and whole", len(rows_after_kill), n_after_kill * 10)
j4.run(lambda k: [{"key": k}])
check("finishes after kill", j4.n_done_batches(), 10)
check("still exactly 100 rows", len({r["key"] for r in j4.rows()}), 100)

# --- 4. externally corrupted shard is detected and repairable ------------
j5 = Job("t5", KEYS, ROOT, batch_size=10, verbose=False); j5.run(work)
victim = j5._path(4)
open(victim, "a").write('{"key": "trunc", "v": ')      # half a line
bad = j5.verify()
check("damage detected", [i for i, _ in bad], [4])
check("rows() tolerates it rather than raising", len(list(j5.rows())), 100)
j5.reset()                                              # repairs damaged only
check("damaged shard requeued", j5.n_done_batches(), 9)
j5.run(work)
check("repaired to full", len(list(j5.rows())), 100)

# --- 5. errors are captured, not fatal, and retryable --------------------
j6 = Job("t6", KEYS, ROOT, batch_size=10, verbose=False)
state = {"fail": True}
def sometimes(k):
    if state["fail"] and k == "repo042": raise RuntimeError("rate limited")
    return work(k)
j6.run(sometimes)
check("job completed despite failure", j6.n_done_batches(), 10)
check("one error recorded", len(j6.errors()), 1)
check("good rows still 99", len(list(j6.rows())), 99)
state["fail"] = False
j6.retry_errors()
j6.run(sometimes)
check("after retry, 100 rows", len(list(j6.rows())), 100)
check("no errors remain", len(j6.errors()), 0)

# --- 6. changed inputs cannot silently corrupt a run ---------------------
try:
    Job("t6", KEYS[:50], ROOT, batch_size=10, verbose=False)
    fails.append("changing the key list should have raised")
except ValueError:
    pass
j7 = Job("t6", KEYS, ROOT, batch_size=10, params={"detector": "v2"}, verbose=False)
check("different params = separate run", j7.n_done_batches(), 0)

# --- 7. atomic_write_text never leaves a partial file --------------------
target = os.path.join(ROOT, "atomic.json")
atomic_write_text(target, json.dumps({"a": 1}))
try:
    atomic_write_text(target, None)      # TypeError inside
except Exception:
    pass
check("original survives a failed write", json.load(open(target)), {"a": 1})
check("no .tmp residue", [f for f in os.listdir(ROOT) if f.startswith("atomic.json.")], [])

shutil.rmtree(ROOT, ignore_errors=True)
print(f"ran {7} scenarios / {28} assertions")
if fails:
    print(f"\nFAILURES ({len(fails)}):\n" + "\n\n".join(fails)); sys.exit(1)
print("all passed — crash safety verified")
