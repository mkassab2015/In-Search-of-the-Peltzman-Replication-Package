#!/usr/bin/env python3
"""Fetch the two public corpora the study is built from.

Neither is redistributed in this package. Both are public.

  zenodo     the GitHub Actions workflow file histories (treatment dates)
  gharchive  the GitHub event stream (outcomes)

Examples:
    python scripts/fetch_sources.py zenodo --record 20340547 --out data/raw
    python scripts/fetch_sources.py gharchive --start 2019-07-01 \
        --end 2025-06-30 --out data/raw/gharchive --dry-run

Downloads resume: a file already present with a non-zero size is skipped, and
each file is written to a .part and renamed on success, so an interrupted run
never leaves a truncated file behind.

Standard library only.
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

UA = {"User-Agent": "msr2027-replication/1.0"}
GHA = "https://data.gharchive.org/{y}-{m:02d}-{d:02d}-{h}.json.gz"


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout)


def download(url, path, timeout=120):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return "skip"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".part"
    try:
        with _get(url, timeout) as r, open(tmp, "wb") as fh:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
        os.replace(tmp, path)
        return "ok"
    except urllib.error.HTTPError as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        return f"http {e.code}"
    except Exception as e:                      # noqa: BLE001
        if os.path.exists(tmp):
            os.remove(tmp)
        return f"error {type(e).__name__}"


def head_size(url):
    req = urllib.request.Request(url, headers=UA, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return int(r.headers.get("Content-Length") or 0)
    except Exception:                            # noqa: BLE001
        return 0


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024


def cmd_zenodo(args):
    api = f"https://zenodo.org/api/records/{args.record}"
    print(f"reading {api}")
    try:
        with _get(api) as r:
            rec = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"could not read the record: HTTP {e.code}. Check the record id.")
        return 2
    except Exception as e:                       # noqa: BLE001
        print(f"could not reach Zenodo: {type(e).__name__}. "
              f"Check network access and proxy settings.")
        return 2

    title = rec.get("metadata", {}).get("title", "(no title)")
    files = rec.get("files", [])
    total = sum(f.get("size", 0) for f in files)
    print(f"record {args.record}: {title}")
    print(f"{len(files)} file(s), {human(total)}\n")

    if args.dry_run:
        for f in files:
            print(f"  {f.get('key'):<52} {human(f.get('size', 0))}")
        return 0

    rc = 0
    for f in files:
        key = f.get("key")
        url = f.get("links", {}).get("self")
        if not url:
            continue
        out = os.path.join(args.out, key)
        status = download(url, out)
        print(f"  {status:<10} {key}")
        if status not in ("ok", "skip"):
            rc = 1
    return rc


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def cmd_gharchive(args):
    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    if end < start:
        print("end is before start")
        return 2

    urls = [(GHA.format(y=d.year, m=d.month, d=d.day, h=h),
             os.path.join(args.out, f"{d.isoformat()}-{h}.json.gz"))
            for d in daterange(start, end) for h in range(24)]

    print(f"{start} to {end}: {len(urls)} hourly files")

    if args.dry_run:
        sample = urls[:: max(1, len(urls) // 8)][:8]
        sizes = [head_size(u) for u, _ in sample]
        sizes = [s for s in sizes if s]
        if sizes:
            mean = sum(sizes) / len(sizes)
            print(f"sampled {len(sizes)} file(s), mean {human(mean)}")
            print(f"estimated total: {human(mean * len(urls))}")
        print("\nThis is the full event stream. Most replications do not need "
              "all of it:\nfilter to the repositories in the frame, or fetch "
              "month by month and\nreduce each month before fetching the next.")
        return 0

    done = failed = 0
    for i, (url, out) in enumerate(urls, 1):
        status = download(url, out)
        if status in ("ok", "skip"):
            done += 1
        else:
            failed += 1
            print(f"  {status:<10} {os.path.basename(out)}")
        if i % 100 == 0 or i == len(urls):
            print(f"  {i}/{len(urls)}  ok={done} failed={failed}")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    z = sub.add_parser("zenodo", help="workflow file histories")
    z.add_argument("--record", default="20340547")
    z.add_argument("--out", default="data/raw")
    z.add_argument("--dry-run", action="store_true")
    z.set_defaults(func=cmd_zenodo)

    g = sub.add_parser("gharchive", help="GitHub event stream")
    g.add_argument("--start", default="2019-07-01")
    g.add_argument("--end", default="2025-06-30")
    g.add_argument("--out", default="data/raw/gharchive")
    g.add_argument("--dry-run", action="store_true")
    g.set_defaults(func=cmd_gharchive)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
