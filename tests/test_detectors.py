import sys, pathlib, yaml
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'src'))
from detectors import classify, prefilter, _get_triggers, first_adoption, bundling_rate, cohort_table

fails = []
def check(name, got, want):
    if got != want:
        fails.append("%s\n    got  %r\n    want %r" % (name, got, want))

# --- the YAML `on:` boolean trap -----------------------------------------
doc = yaml.safe_load("on:\n  pull_request:\n    branches: [main]\njobs: {}\n")
check("PyYAML really does turn `on` into True", set(doc.keys()), {True, "jobs"})
check("_get_triggers survives it", _get_triggers(doc), {"pull_request"})
check("quoted 'on' also works", _get_triggers(yaml.safe_load("'on': [push, pull_request]\n")), {"push", "pull_request"})
check("string form", _get_triggers(yaml.safe_load("'on': pull_request\n")), {"pull_request"})

# --- real-shaped workflows ------------------------------------------------
W_TEST = """
name: CI
on:
  pull_request:
  push:
    branches: [main]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e .
      - run: pytest -q --cov=src
"""
t, m = classify(W_TEST)
check("test job detected", "T1_test" in t, True)
check("triggers parsed", m["triggers"], {"pull_request", "push"})

W_LINT_PUSH_ONLY = """
name: Lint
on:
  push:
    branches: [main]
jobs:
  lint:
    steps: [{run: ruff check .}]
"""
t, m = classify(W_LINT_PUSH_ONLY)
check("push-only lint is not a PR gate", t, set())
check("rejection reason recorded", m["reason"], "no pull_request trigger")

W_MQ = """
name: Merge queue checks
on:
  merge_group:
  pull_request:
jobs:
  t: {steps: [{run: go test ./...}]}
"""
t, _ = classify(W_MQ)
check("merge queue + go test", t, {"T6_mergequeue", "T1_test"})

W_COV = """
'on': [pull_request]
jobs:
  c:
    steps:
      - uses: codecov/codecov-action@v4
"""
t, _ = classify(W_COV)
check("coverage action", t, {"T3_coverage"})

W_TYPES = """
'on': [pull_request]
jobs:
  t: {steps: [{run: mypy src/}]}
"""
check("mypy", classify(W_TYPES)[0], {"T4_types"})

W_STALE = """
name: Stale
'on': [pull_request, schedule]
jobs:
  s: {steps: [{run: npm test}]}
"""
check("housekeeping workflow excluded", classify(W_STALE)[0], set())

W_BROKEN = "on: [pull_request\njobs: {{{ pytest"
t, m = classify(W_BROKEN)
check("malformed YAML does not raise", t, set())
check("malformed reason", m["reason"].startswith("unparseable"), True)

check("empty file", classify("")[0], set())
check("prefilter is cheap and text-only", prefilter("run: cargo clippy"), {"T2_lint"})
# guard against the tsc regex matching inside other words
check("tsc not matched inside words", prefilter("run: echo artifacts-tscan"), set())

# --- cohort / bundling ----------------------------------------------------
obs = [
    ("a", "T1_test", "2023-05"), ("a", "T1_test", "2023-09"),   # keep earliest
    ("a", "T2_lint", "2023-06"),                                 # bundled (+1)
    ("b", "T1_test", "2022-01"), ("b", "T2_lint", "2023-11"),    # far apart
    ("c", "T1_test", "2024-02"),                                 # single only
    ("d", "T3_coverage", "2021-12"), ("d", "T4_types", "2022-02"),  # bundled (+2)
]
ad = first_adoption(obs)
check("earliest adoption wins", ad["a"]["T1_test"], "2023-05")
rate, multi, bundled = bundling_rate(ad, window_months=3)
check("repos with 2+ safeguards", multi, 3)
check("bundled repos", bundled, 2)
check("bundling rate", round(rate, 4), round(2/3, 4))
check("year boundary handled (d: 2021-12 -> 2022-02)", bundled >= 2, True)
check("cohort table", cohort_table(ad, "T1_test"), {"2022-01": 1, "2023-05": 1, "2024-02": 1})

print("ran %d checks" % (10 + 14))
if fails:
    print("\nFAILURES (%d):\n" % len(fails)); print("\n\n".join(fails)); sys.exit(1)
print("all passed")
