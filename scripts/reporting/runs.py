"""Run catalogue: one card per benchmark / ramp / auth run (used by results/index.html and the combined report)."""
import os

from .common import RESULTS, esc, jload, kv, metric, name_of, read, runs
from . import auth


def _stacks(env):
    return " · ".join(name_of(s) for s in env.get("stacks", "").split())


def bench_card(root, name):
    p = os.path.join(root, "benchmarks", name)
    env = kv(os.path.join(p, "env.txt"))
    best = {}
    for stack in env.get("stacks", "").split():
        for wl in ("pk", "mixed"):
            rate = metric(jload(os.path.join(p, "k6", f"{stack}-{wl}-r1.json")), "http_reqs").get("rate")
            if rate and rate > best.get(wl, (0, ""))[0]:
                best[wl] = (rate, stack)
    leaders = "; ".join(f"{wl}: {name_of(s)} {v:,.0f}/s" for wl, (v, s) in best.items()) or "–"
    link = f"benchmarks/{name}/report.html" if os.path.exists(os.path.join(p, "report.html")) else None
    return [("Auth", env.get("auth_mode", "none")), ("Stacks", _stacks(env)), ("Workloads", env.get("workloads", "")),
            ("Load", f"{env.get('vus', '')} VUs · {env.get('duration', '')}"), ("Leaders", leaders)], link


def ramp_card(root, name):
    p = os.path.join(root, "ramps", name)
    env = kv(os.path.join(p, "env.txt"))
    peaks = []
    for stack in env.get("stacks", "").split():
        for wl in env.get("workloads", "").split():
            j = jload(os.path.join(p, "k6", f"{stack}-{wl}.json"))
            if j and j.get("steps"):
                peaks.append(f"{name_of(stack)} {max(s['count'] for s in j['steps']) / j['stepSeconds']:,.0f}/s")
    rates = env.get("rates", "").split(",")
    link = f"ramps/{name}/ramp-report.html" if os.path.exists(os.path.join(p, "ramp-report.html")) else None
    return [("Auth", env.get("auth_mode", "none")), ("Stacks", _stacks(env)), ("Workloads", env.get("workloads", "")),
            ("Steps", f"{rates[0]}–{rates[-1]} req/s × {env.get('step_dur', '')} s"), ("Peak served", " · ".join(peaks) or "–")], link


def auth_card(root, name):
    rows = auth.contract_rows(os.path.join(root, "auth", name))
    ok = sum(1 for r in rows.values() if r[3])
    return [("Stacks tested", " · ".join(name_of(s) for s in rows)), ("All checks passed", f"{ok} of {len(rows)} stacks")], \
        (f"auth/{name}/summary.md" if rows else None)


KINDS = [
    ("benchmarks", "Benchmarks", "100 constant VUs, closed model: throughput, latency, CPU and memory per stack and workload.", bench_card),
    ("ramps", "Ramp tests", "Open-model load ramp: where each stack breaks and the highest load with p95 under the target.", ramp_card),
    ("auth", "Auth tests", "JWT contract checks (401 cases, alg confusion, expiry) and the normal API contract with a token.", auth_card),
]


def catalogue(root=RESULTS, link_prefix=""):
    """HTML cards for every run, grouped by kind, newest first."""
    out = []
    for kind, title, sub, fn in KINDS:
        names = runs(kind, root)
        cards = []
        for n in names:
            cells, link = fn(root, n)
            dl = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in cells)
            a = f"<a class='open' href='{esc(link_prefix + link)}'>Open report</a>" if link else "<span class='muted'>no report</span>"
            cards.append(f"<article class='run'><header><b>{esc(n)}</b>{a}</header><dl>{dl}</dl><p class='path'><code>results/{kind}/{esc(n)}/</code></p></article>")
        body = f"<div class='runs'>{''.join(cards)}</div>" if cards else "<p class='muted'>No runs yet.</p>"
        out.append(f"<section><h2>{esc(title)}</h2><p class='sub'>{esc(sub)}</p>{body}</section>")
    return "".join(out)
