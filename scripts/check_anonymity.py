#!/usr/bin/env python3
"""Scan a replication package for identifying information.

Usage:
    python scripts/check_anonymity.py <root>
    python scripts/check_anonymity.py <root> --names Smith jsmith --terms "Some University"

Names and institutions are passed at the command line and are never stored in
this file: a hard-coded list of your own affiliations would itself deanonymise
the package. Exits non-zero if anything is found. Run it before depositing and
again on the extracted archive.
"""
import argparse
import os
import zipfile
import re
import sys

SELF = os.path.basename(__file__)
SKIP_DIRS = {".git", "__pycache__", ".ipynb_checkpoints", "node_modules"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".pdf", ".gz", ".zip", ".parquet",
            ".woff", ".woff2", ".ttf"}
# Office files are zip containers: scanning the compressed bytes as text yields
# only noise. Their XML parts are checked by scan_office() instead.
OFFICE_EXT = {".xlsx", ".xlsm", ".xls", ".docx", ".pptx"}

# Data files hold mined content: public repository names and the workflow YAML
# the detectors and the labeller read. Those legitimately contain third-party
# action references, bot addresses, paths and organization names, so files
# under these directories are scanned only for probes that identify the
# submitting author. Code and prose get the full probe set.
DATA_DIRS = {"data", "results", "state"}
DATA_EXT = {".json", ".csv", ".tsv", ".parquet"}
IDENTITY_LABELS = {"author name", "flagged term", "orcid"}

PATTERNS = [
    ("email address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("github user URL", re.compile(
        r"github\.com/(?!features|about|settings|orgs|search|marketplace|topics)[A-Za-z0-9_-]+/")),
    ("personal home path", re.compile(
        r"/(?:Users|home)/(?!claude\b|runner\b)[A-Za-z0-9._-]+/")),
    ("windows user path", re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+")),
    ("orcid", re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b")),
    ("git remote", re.compile(r"git@[\w.-]+:")),
    ("affiliation word", re.compile(
        r"\b(?:univ(?:ersity|ersit[ée])?|institute of technology|"
        r"laborator(?:y|ies)|department of|faculty of)\b", re.I)),
    ("funding", re.compile(r"\b(?:grant|award)\s+(?:no\.?|number)\b", re.I)),
    ("acknowledgement", re.compile(r"\backnowledge?ments?\b", re.I)),
    ("author field", re.compile(r"^\s*(?:author|copyright)\s*[:=]", re.I)),
]

# Identical for every Colab user, so not identifying.
BENIGN = re.compile(r"/content/drive/MyDrive")


def scan_office(path, root, probes):
    """Scan the XML parts of an Office file rather than the compressed
    container bytes.

    docProps holds the author metadata and is scanned with every probe. The
    sheet parts hold the sampled workflow text the labeller read, which is
    quoted from public repositories: it legitimately contains third-party
    action references, repository URLs and bot addresses, so those parts are
    scanned only for probes that identify the submitting author.
    """
    found = []
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        return [(os.path.relpath(path, root), 0, "unreadable office file", "")]
    with zf:
        for member in zf.namelist():
            if not member.endswith((".xml", ".rels")):
                continue
            meta = member.startswith("docProps")
            use = probes if meta else [p for p in probes
                                       if p[0] in IDENTITY_LABELS]
            if not use:
                continue
            try:
                text = zf.read(member).decode("utf-8", "ignore")
            except (OSError, KeyError):
                continue
            for label, pat in use:
                for m in pat.finditer(text):
                    if BENIGN.search(m.group(0)):
                        continue
                    found.append((os.path.relpath(path, root) + "!" + member,
                                  0, label, m.group(0)[:80]))
    return found


def scan(root, names, terms):
    probes = list(PATTERNS)
    for label, words in (("author name", names), ("flagged term", terms)):
        words = [w for w in words if w.strip()]
        if words:
            alts = "|".join(re.escape(w) for w in words)
            probes.append((label, re.compile(rf"(?:{alts})", re.I)))

    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if fn == SELF or ext in SKIP_EXT:
                continue
            path = os.path.join(dirpath, fn)
            if ext in OFFICE_EXT:
                hits.extend(scan_office(path, root, probes))
                continue
            top = os.path.relpath(path, root).split(os.sep)[0]
            use = probes
            if top in DATA_DIRS and ext in DATA_EXT:
                use = [p for p in probes if p[0] in IDENTITY_LABELS]
                if not use:
                    continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                for label, pat in use:
                    for m in pat.finditer(line):
                        if BENIGN.search(m.group(0)):
                            continue
                        hits.append((os.path.relpath(path, root), i,
                                     label, m.group(0)[:80]))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--names", nargs="*", default=[],
                    help="author surnames, given names and usernames")
    ap.add_argument("--terms", nargs="*", default=[],
                    help="any other string that would identify you")
    args = ap.parse_args()

    hits = scan(args.root, args.names, args.terms)
    rc = 0

    if os.path.isdir(os.path.join(args.root, ".git")):
        print("FAIL  a .git directory is present. It carries commit author "
              "names and emails. Deposit a clean export, not a clone.\n")
        rc = 1

    if hits:
        print(f"FAIL  {len(hits)} item(s) to review:\n")
        for rel, line, label, text in hits:
            print(f"  {rel + ':' + str(line):<46} {label:<18} {text}")
        rc = 1
    elif rc == 0:
        print("PASS  nothing identifying found in the file contents.")

    print("\nNot checked by this script, check by hand:")
    print("  - the deposit record's uploader name and ORCID")
    print("  - notebook outputs and execution metadata")
    print("  - file owner and timestamp fields inside the archive")
    print("  - image EXIF and PDF producer fields")
    return rc


if __name__ == "__main__":
    sys.exit(main())
