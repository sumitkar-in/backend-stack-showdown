#!/usr/bin/env python3
"""One-off: move results from the old flat layout into results/{benchmarks,ramps,auth}/<date>_<time>_<label>/
with raw files in k6/ stats/ postgres/ contract/ logs/. Safe to re-run (already-organised runs are skipped).
usage: organize-results.py [results-dir]"""
import datetime
import os
import re
import shutil
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
ROOT = os.path.abspath(ROOT)
TS = re.compile(r"^(?:ramp-|auth-)?(\d{8})-(\d{6})$")
RULES = [  # (regex on file name, sub-directory)
    (r"^(stats-.*\.raw)$", "stats"),
    (r"^(pgstmt-|pgdb-|pgconns-|postgres\.).*", "postgres"),
    (r"^(smoke-|auth-|api-).*\.txt$", "contract"),
    (r"^(build-|app-|inspect-).*", "logs"),
    (r"^(k6-|warm-).*", "k6"),
]


def kv(path):
    try:
        return dict(l.rstrip("\n").split("=", 1) for l in open(path) if "=" in l)
    except OSError:
        return {}


def kind_of(path):
    env = kv(os.path.join(path, "env.txt"))
    if os.path.exists(os.path.join(path, "summary.md")):
        return "auth"
    if "rates" in env:
        return "ramps"
    if env:
        return "benchmarks"
    return None


def stamp(name, path):
    m = TS.match(name)
    if m:
        d, t = m.groups()
        return f"{d[:4]}-{d[4:6]}-{d[6:]}_{t[:4]}"
    st = os.stat(os.path.join(path, "run.log") if os.path.exists(os.path.join(path, "run.log")) else path)
    return datetime.datetime.fromtimestamp(getattr(st, "st_birthtime", st.st_mtime)).strftime("%Y-%m-%d_%H%M")


def label_for(kind, name, path):
    env = kv(os.path.join(path, "env.txt"))
    if TS.match(name):
        if kind == "benchmarks":
            n = len(env.get("stacks", "").split())
            return {5: "all-stacks", 4: "four-stacks"}.get(n, "")
        if kind == "ramps":
            return "-".join(env.get("stacks", "").split()) + "-" + "-".join(env.get("workloads", "").split())
        return ""
    label = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    label = re.sub(r"^(ramp|auth)-", "", label)
    return re.sub(r"^cmp-", "compare-", label)


def move_into(run, dst):
    for f in sorted(os.listdir(run)):
        src = os.path.join(run, f)
        if os.path.isdir(src):
            continue
        target = None
        if f.endswith(".json") and not f.startswith("report"):
            target = "k6"
        else:
            for rx, sub in RULES:
                if re.match(rx, f):
                    target = sub
                    break
        if target:
            os.makedirs(os.path.join(dst, target), exist_ok=True)
        shutil.move(src, os.path.join(dst, target, f) if target else os.path.join(dst, f))


def main():
    for kind in ("benchmarks", "ramps", "auth"):
        os.makedirs(os.path.join(ROOT, kind), exist_ok=True)
    for name in sorted(os.listdir(ROOT)):
        run = os.path.join(ROOT, name)
        if not os.path.isdir(run) or name in ("benchmarks", "ramps", "auth", "experiments"):
            continue
        kind = kind_of(run)
        if kind is None:
            print(f"skip (unrecognised): {name}")
            continue
        label = label_for(kind, name, run)
        new = stamp(name, run) + (f"_{label}" if label else "")
        dst = os.path.join(ROOT, kind, new)
        n = 2
        while os.path.exists(dst):
            dst = os.path.join(ROOT, kind, f"{new}-{n}")
            n += 1
        os.makedirs(dst)
        move_into(run, dst)
        # top-level files (env.txt, cells.tsv, run.log, report*.html, ...) go along
        for f in os.listdir(run):
            shutil.move(os.path.join(run, f), os.path.join(dst, f))
        os.rmdir(run)
        print(f"{name}  ->  {kind}/{os.path.basename(dst)}")


if __name__ == "__main__":
    main()
