"""One page with everything: scorecard, benchmark, ramps, auth, and the run catalogue (results/report.html)."""
import os

from . import auth, bench, ramp, runs as runcat
from .common import (RESULTS, STACKS, chip, esc, fms, fnum, hbar_card, grid, kv, name_of, nav, page, runs, table, warn_box, write)


def _rank(root, kind, key):
    names = runs(kind, root)
    scored = [(key(kv(os.path.join(root, kind, n, "env.txt"))), n) for n in names]
    return [os.path.join(root, kind, n) for _, n in sorted(scored, reverse=True)]


def pick_bench(root):
    """Best full-coverage no-auth run: most stacks x workloads, newest wins ties."""
    ranked = _rank(root, "benchmarks", lambda e: (e.get("auth_mode", "none") == "none", len(e.get("stacks", "").split()) * len(e.get("workloads", "").split())))
    return ranked[0] if ranked else None


def pick_ramps(root):
    return _rank(root, "ramps", lambda e: (len(e.get("stacks", "").split()), 0))


def _ramp_best(ramp_facts, wl):
    """Per stack, the strongest result for a workload across all ramp runs (later runs probe higher rates)."""
    best = {}
    for facts in ramp_facts:
        for st, f in facts.get(wl, {}).items():
            if st not in best or (f["max_ok"] or 0) > (best[st]["max_ok"] or 0):
                best[st] = f
    return best


def scorecard(bench_facts, ramp_facts, auth_facts, target):
    stacks = sorted({s for s in (bench_facts["ran"] if bench_facts else [])} | {s for rf in ramp_facts for wl in rf.values() for s in wl}
                    | set(auth_facts["contract"]), key=lambda s: STACKS.get(s, ("", "", 99))[2])
    wl = "pk" if any("pk" in rf for rf in ramp_facts) else next((w for rf in ramp_facts for w in rf), None)
    rbest = _ramp_best(ramp_facts, wl) if wl else {}
    m = bench_facts["med"] if bench_facts else (lambda *a: None)
    rows = []
    for s in stacks:
        r = rbest.get(s)
        c = auth_facts["contract"].get(s)
        ov = auth_facts["overhead"].get(s)
        rows.append([
            chip(s),
            fnum(m(s, "mixed", "ok_rps")) if bench_facts else "–", fms(m(s, "pk", "p95")) if bench_facts else "–",
            fnum(m(s, "pk", "rps_per_core")) if bench_facts else "–",
            fnum(bench_facts["geo"].get(s), 1) if bench_facts else "–",
            fnum(r["max_ok"]) if r else "–",
            (fnum(r["target_load"]) if r and r["target_load"] else "never") if r else "–",
            fnum(r["breaks_at"]) if r and r["breaks_at"] else ("not reached" if r else "–"),
            esc(r["limiter"]) if r else "–",
            ("<span class='pass'>PASS</span>" if c[3] else "<span class='fail'>FAIL</span>") if c else "–",
            f"{ov:+.1f}%" if ov is not None else "–",
        ])
    heads = ["Stack", "Mixed req/s", "PK p95 ms", "PK req/s per core", "Throughput index", f"Ramp {wl or ''}: max healthy req/s",
             f"Ramp: max with p95 ≤ {target:g} ms", "Ramp: breaks at", "Limiting factor", "Auth contract", "JWT cost (median)"]
    return table(heads, rows, "score")


def build(root=RESULTS, bench_dir=None, ramp_dirs=None, pair=None):
    bench_dir = bench_dir or pick_bench(root)
    ramp_dirs = ramp_dirs if ramp_dirs is not None else pick_ramps(root)
    pair = pair or auth.find_pair(root)
    parts, top, notes = [], [("overview", "Overview")], []

    # ---- benchmark
    b_links = b_html = b_facts = None
    if bench_dir:
        run = bench.load(bench_dir)
        b_links, b_html, b_facts = bench.render(run, "bench-")
        top.append(("benchmark", "Benchmark"))
        notes.append(f"benchmark <code>{esc(run['name'])}</code>")
    # ---- ramps
    ramp_runs = [ramp.load(d) for d in ramp_dirs]
    ramp_blocks, ramp_facts = [], []
    for k, rr in enumerate(ramp_runs):
        links, body, facts = ramp.render(rr, f"ramp{k}-")
        ramp_facts.append(facts)
        head = (f"<h2>{esc(rr['name'])}</h2><div class='meta'>{ramp.meta_html(rr)}</div>" + nav(links, "sub-nav"))
        ramp_blocks.append(f"<details open><summary>{esc(rr['name'])}</summary>{head}{body}</details>" if k == 0 else
                           f"<details><summary>{esc(rr['name'])}</summary>{head}{body}</details>")
    if ramp_runs:
        top.append(("ramp", "Ramp"))
        notes.append("ramp " + ", ".join(f"<code>{esc(r['name'])}</code>" for r in ramp_runs))
    # ---- auth
    contract = auth.contract_latest(root)
    a_links, a_html, a_facts = auth.render(contract, pair, "auth-")
    top.append(("auth", "Auth"))
    top.append(("runs", "All runs"))
    target = ramp_runs[0]["target"] if ramp_runs else 0.5

    # ---- overview
    leaders = ""
    if b_facts and b_facts["leaders"].get("mixed"):
        mixed = b_facts["leaders"]["mixed"]
        leaders = (f"<p class='lede'><b>{esc(name_of(mixed[0][0]))}</b> leads the mixed workload at <b>{fnum(mixed[0][1])}</b> req/s (100 VUs, closed model). "
                   + "Ranking: " + " &gt; ".join(f"{esc(name_of(s))} ({fnum(v)})" for s, v in mixed) + ".</p>")
    cards = ""
    if b_facts:
        ran = b_facts["ran"]
        cards = grid([hbar_card("Mixed workload", "successful req/s, higher is better", [(s, b_facts["med"](s, "mixed", "ok_rps")) for s in ran], " req/s", 0),
                      hbar_card("PK lookup", "successful req/s, higher is better", [(s, b_facts["med"](s, "pk", "ok_rps")) for s in ran], " req/s", 0),
                      hbar_card("PK lookup p95", "milliseconds, lower is better", [(s, b_facts["med"](s, "pk", "p95")) for s in ran], " ms", 1, "low"),
                      hbar_card("Efficiency (PK)", "req/s per app CPU core", [(s, b_facts["med"](s, "pk", "rps_per_core")) for s in ran], "", 0)])
    overview = f"""<section id="overview"><h2>Overview</h2>
<p class="sub">Every stack on the same API, PostgreSQL 17 data (1,000 devices, 1,000,000 readings), Docker limits (2 vCPU / 4 GiB per app) and k6 load. Numbers below come from: {', '.join(notes) or 'no runs yet'}.</p>
{leaders}{warn_box([f"{b_facts['warnings']} validity note(s) in the benchmark run; see the Benchmark section."] if b_facts and b_facts["warnings"] else [])}
{scorecard(b_facts, ramp_facts, a_facts, target)}
<p class="sub" style="margin-top:8px">Throughput index: geometric mean of each workload's throughput relative to the best stack (best = 100). Ramp columns use the strongest result across all ramp runs for the workload. JWT cost: median req/s change with auth on, single short runs (noisy).</p>
{cards}</section>"""

    sections = [overview]
    if b_html:
        sections.append(f"<div class='part' id='benchmark'><h1>Benchmark</h1><div class='meta'>{bench.meta_html(run)}</div>{nav(b_links, 'sub-nav')}{b_html}</div>")
    if ramp_blocks:
        sections.append(f"<div class='part' id='ramp'><h1>Ramp: where each stack breaks</h1><p class='sub'>Open model: a fixed request rate per step, so latency and errors show saturation. "
                        f"The first run is the broadest; the others probe higher rates.</p>{''.join(ramp_blocks)}</div>")
    sections.append(f"<div class='part' id='auth'><h1>Authentication</h1>{a_html}</div>")
    sections.append(f"<div class='part' id='runs'><h1>All runs</h1>{runcat.catalogue(root)}</div>")

    body = (f"<header><h1>SensorPulse benchmark report</h1><p>{esc(', '.join(name_of(s) for s in (b_facts['ran'] if b_facts else [])) or 'No stacks yet')}: "
            f"identical API, data and Docker limits.</p></header>{nav(top)}{''.join(sections)}"
            f"<footer>Generated by scripts/report.py · combined view of the runs listed in the overview.</footer>")
    return page("SensorPulse Report", body)


def write_combined(root=RESULTS, **kw):
    return write(os.path.join(root, "report.html"), build(root, **kw))
