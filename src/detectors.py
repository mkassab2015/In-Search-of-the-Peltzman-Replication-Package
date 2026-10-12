"""
Peltzman Protocol - safeguard detectors.
Classifies a GitHub Actions workflow file (raw YAML text) into safeguard
categories, and computes cohort/bundling statistics from adoption dates.

Design notes
------------
* Detection is two-stage: a cheap regex prefilter over raw text, then a YAML
  parse only for files that matched something. On ~10M historical file
  versions the prefilter is what makes NB1 finish in hours instead of days.
* The YAML `on:` key is parsed by PyYAML (YAML 1.1) as the BOOLEAN True, not
  the string "on". Every workflow parser that forgets this silently finds no
  triggers. handled in `_get_triggers`.
"""
import re
from collections import defaultdict

# --- safeguard signatures -------------------------------------------------
# Ordered dict of treatment id -> list of compiled patterns over raw file text.
_RAW = {
    "T1_test": [
        r"\bpytest\b", r"\bvitest\b", r"\bjest\b", r"\bgo\s+test\b",
        r"\bmvn\b[^\n]*\btest\b", r"\bgradle\w*\b[^\n]*\btest\b",
        r"\bcargo\s+test\b", r"\brspec\b", r"\bnpm\s+(?:run\s+)?test\b",
        r"\byarn\s+test\b", r"\btox\b", r"\bdotnet\s+test\b",
        r"\bphpunit\b", r"\bctest\b", r"\bpython\s+-m\s+unittest\b",
        r"\bbundle\s+exec\s+rspec\b",
    ],
    "T2_lint": [
        r"\beslint\b", r"\bruff\b", r"\bflake8\b", r"\bgolangci-lint\b",
        r"\bcheckstyle\b", r"\bspotbugs\b", r"\bcargo\s+clippy\b",
        r"\brubocop\b", r"\bpylint\b", r"\bshellcheck\b", r"\bbiome\s+lint\b",
    ],
    "T3_coverage": [
        r"codecov/codecov-action", r"coverallsapp/", r"\bjacoco\b",
        r"--cov-fail-under", r"--fail-under", r"\bcoveralls\b",
        r"\bcodecov\b",
    ],
    "T4_types": [
        r"\bmypy\b", r"\bpyright\b", r"(?<![\w-])tsc(?![\w-])",
        r"\bpsalm\b", r"\bphpstan\b", r"\bflow\s+check\b",
    ],
    "T6_mergequeue": [
        r"\bmerge_group\b",
    ],
}
PATTERNS = {k: [re.compile(p, re.I) for p in v] for k, v in _RAW.items()}
TREATMENTS = list(PATTERNS.keys())

# YAML loading. PyYAML's pure-Python SafeLoader runs ~1.8 ms on a typical
# workflow; the libyaml-backed CSafeLoader does the same file in ~0.19 ms.
# Across millions of files that is the difference between two hours and twenty
# minutes, so prefer it and fall back only if the C extension is absent.
import yaml
try:
    _LOADER = yaml.CSafeLoader
    YAML_BACKEND = "libyaml (CSafeLoader)"
except AttributeError:                       # PyYAML built without libyaml
    _LOADER = yaml.SafeLoader
    YAML_BACKEND = "pure python (SafeLoader)"

def _yaml_load(text):
    return yaml.load(text, Loader=_LOADER)


# Files that are workflow definitions but never act as a PR gate.
_NON_GATE_HINT = re.compile(r"\b(stale|greetings|labeler|first-interaction)\b", re.I)


def prefilter(text):
    """Cheap pass over raw text. Returns the set of treatments whose signature
    appears anywhere in the file. No YAML parsing."""
    hits = set()
    for t, pats in PATTERNS.items():
        for p in pats:
            if p.search(text):
                hits.add(t)
                break
    return hits


def _get_triggers(doc):
    """Return the set of trigger names for a parsed workflow document.

    PyYAML resolves the bare key `on` to the boolean True (YAML 1.1). Look
    under both spellings or you will find no triggers at all.
    """
    if not isinstance(doc, dict):
        return set()
    node = doc.get("on", doc.get(True))
    if node is None:
        return set()
    if isinstance(node, str):
        return {node}
    if isinstance(node, list):
        return {str(x) for x in node}
    if isinstance(node, dict):
        return {str(k) for k in node.keys()}
    return set()


def classify(text, require_pr_trigger=True):
    """Full classification of one workflow file version.

    Returns (treatments:set, meta:dict). `meta` carries the triggers found and
    why a file was rejected, so the prototype can be audited by hand.
    """
    meta = {"triggers": set(), "parsed": False, "reason": None}
    hits = prefilter(text)
    if not hits:
        meta["reason"] = "no signature"
        return set(), meta

    try:
        doc = _yaml_load(text)
        meta["parsed"] = True
    except Exception as e:                       # malformed historical version
        meta["reason"] = "unparseable: %s" % type(e).__name__
        return set(), meta

    triggers = _get_triggers(doc)
    meta["triggers"] = triggers

    # merge_group is a trigger, not a job step: judge it on triggers alone.
    out = set()
    if "merge_group" in triggers:
        out.add("T6_mergequeue")

    gate_hits = hits - {"T6_mergequeue"}
    if gate_hits:
        if require_pr_trigger and "pull_request" not in triggers \
                and "pull_request_target" not in triggers:
            meta["reason"] = "no pull_request trigger"
        elif _NON_GATE_HINT.search(str(doc.get("name", ""))):
            meta["reason"] = "housekeeping workflow"
        else:
            out |= gate_hits
    return out, meta


# --- cohort / bundling ----------------------------------------------------

def _m(ym):
    """'YYYY-MM' -> integer month index, for arithmetic."""
    y, mth = ym.split("-")
    return int(y) * 12 + int(mth) - 1


def first_adoption(observations):
    """observations: iterable of (repo, treatment, 'YYYY-MM').
    Returns {repo: {treatment: earliest 'YYYY-MM'}}."""
    out = defaultdict(dict)
    for repo, t, ym in observations:
        cur = out[repo].get(t)
        if cur is None or _m(ym) < _m(cur):
            out[repo][t] = ym
    return dict(out)


def bundling_rate(adoptions, window_months=3):
    """Share of repos that adopt two or more DISTINCT safeguards within
    +/- `window_months` of each other. This is the day-1 kill criterion: above
    0.50 the per-safeguard design cannot separate treatments.

    Returns (rate, n_repos_with_2plus, n_repos_bundled).
    """
    bundled = multi = 0
    for repo, d in adoptions.items():
        months = sorted(_m(v) for v in d.values())
        if len(months) < 2:
            continue
        multi += 1
        if any(months[i + 1] - months[i] <= window_months
               for i in range(len(months) - 1)):
            bundled += 1
    rate = (bundled / multi) if multi else 0.0
    return rate, multi, bundled


def cohort_table(adoptions, treatment):
    """Adopters per calendar month for one treatment -> {'YYYY-MM': count}."""
    counts = defaultdict(int)
    for repo, d in adoptions.items():
        if treatment in d:
            counts[d[treatment]] += 1
    return dict(sorted(counts.items()))
