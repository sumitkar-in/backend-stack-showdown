"""Closed-model benchmark run (results/benchmarks/<run>): load the data, render its sections."""
import math
import os

from .common import (STACKS, WORKLOADS, chip, esc, fms, fnum, grid, hbar_card, jload, kv, legend, median, metric, name_of, read,
                     steady_state, stats_samples, table, tsv, warn_box, wl_name)


# ---------------------------------------------------------------- loading
def _bottleneck(d):
    if d["app_cpu"] is None:
        return "n/a"
    if d["app_cpu"] >= 1.7:
        return "app CPU"
    if d["workload"] == "health":
        return "load generator / network"
    if d["db_cpu"] is not None and d["db_cpu"] >= 1.7:
        return "database CPU"
    return "latency-bound (neither saturated)"


def _int(v, default=0):
    """Tolerate a blank field (a failed row-count query) so one bad cell cannot break the whole report."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _cell(out, row):
    stack, wl, rep = row[0], row[1], row[2]
    cell = f"{stack}-{wl}-r{rep}"
    data = jload(os.path.join(out, "k6", cell + ".json")) or {}
    dur, reqs, fails, chk = (metric(data, m) for m in ("http_req_duration", "http_reqs", "http_req_failed", "checks"))
    recv = metric(data, "data_received").get("count", 0)
    samples = stats_samples(os.path.join(out, "stats", f"stats-{cell}.raw"))
    app, db = steady_state(samples["app"]), steady_state(samples["db"])
    d = {
        "stack": stack, "workload": wl, "rep": rep, "ok": bool(reqs),
        "rps": reqs.get("rate", 0), "count": reqs.get("count", 0),
        "fail_rate": fails.get("rate", fails.get("value", 0)) or 0,
        "chk_pass": chk.get("passes", 0), "chk_fail": chk.get("fails", 0),
        "p50": dur.get("med", dur.get("p(50)")), "p90": dur.get("p(90)"), "p95": dur.get("p(95)"),
        "p99": dur.get("p(99)"), "avg": dur.get("avg"), "max": dur.get("max"),
        "recv_mb": recv / 1e6, "bytes_per_req": recv / reqs["count"] if reqs.get("count") else 0,
        "rows_before": _int(row[3]), "rows_after": _int(row[4]), "k6_exit": _int(row[5]),
        "app_cpu": app["cpu"] if app else None, "app_mem": app["mem_peak"] if app else None,
        "db_cpu": db["cpu"] if db else None, "db_mem": db["mem_peak"] if db else None,
        "pgstmt": read(os.path.join(out, "postgres", f"pgstmt-{cell}.txt")).strip(),
        "pgdb": read(os.path.join(out, "postgres", f"pgdb-{cell}.txt")).strip(),
    }
    d["ok_rps"] = d["rps"] * (1 - d["fail_rate"])
    d["rps_per_core"] = d["ok_rps"] / d["app_cpu"] if d["app_cpu"] else None
    d["bound"] = _bottleneck(d)
    return d


def load(out):
    env = kv(os.path.join(out, "env.txt"))
    stacks_info = {r[0]: {"smoke": r[1], "build": int(r[2] or 0), "startup": int(r[3] or 0)} for r in tsv(os.path.join(out, "stacks.tsv"))}
    order = [s for s in env.get("stacks", "").split() if s in stacks_info] or list(stacks_info)
    cells = [_cell(out, r) for r in tsv(os.path.join(out, "cells.tsv"))]
    by = {}
    for c in cells:
        by.setdefault((c["stack"], c["workload"]), []).append(c)
    run = {"dir": out, "name": os.path.basename(out), "env": env, "info": stacks_info, "order": order,
           "ran": [s for s in order if stacks_info[s]["smoke"] in ("pass", "fail")],
           "workloads": env.get("workloads", "").split(), "cells": cells, "by": by}
    run["smoke"] = {}
    for s in order:
        lines = read(os.path.join(out, "contract", f"smoke-{s}.txt")).splitlines()
        run["smoke"][s] = {"pass": sum(1 for l in lines if l.startswith("PASS")), "fail": [l for l in lines if l.startswith("FAIL")]}
    return run


def med(run, stack, wl, key):
    return median(c[key] for c in run["by"].get((stack, wl), []))


def _leaders(run):
    leaders = {}
    for wl in run["workloads"]:
        vals = {s: med(run, s, wl, "ok_rps") for s in run["ran"] if med(run, s, wl, "ok_rps")}
        if vals:
            leaders[wl] = sorted(vals.items(), key=lambda kv_: -kv_[1])
    return leaders


def _geo_index(run, leaders):
    idx = {s: [] for s in run["ran"]}
    for ranking in leaders.values():
        best = ranking[0][1]
        for s, v in ranking:
            idx[s].append(v / best)
    return {s: (math.exp(sum(math.log(x) for x in v) / len(v)) * 100 if v else None) for s, v in idx.items()}


def _warnings(run):
    out, env = [], run["env"]
    for s in run["ran"]:
        if run["smoke"][s]["fail"]:
            out.append(f"{name_of(s)} failed {len(run['smoke'][s]['fail'])} contract smoke check(s); its numbers are not strictly comparable.")
        info = read(os.path.join(run["dir"], "logs", f"inspect-{s}.txt")).split()
        if info and info[0] == "true":
            out.append(f"{name_of(s)} container was OOM-killed.")
        if len(info) > 1 and info[1] != "0":
            out.append(f"{name_of(s)} container restarted {info[1]} time(s).")
    for s in run["order"]:
        if run["info"][s]["smoke"] not in ("pass", "fail"):
            out.append(f"{name_of(s)} did not run: {run['info'][s]['smoke']}.")
    for c in run["cells"]:
        if c["fail_rate"] > 0.01 or c["k6_exit"] != 0:
            out.append(f"{name_of(c['stack'])} / {wl_name(c['workload'])}: error rate {c['fail_rate'] * 100:.2f}%, k6 exit {c['k6_exit']} (a threshold was crossed).")
    for ln in read(os.path.join(run["dir"], "invalid.txt")).split():
        out.append(f"{ln}: still invalid after 3 attempts (the host stalled; test clock off); treat this cell as unreliable.")
    return out


# ---------------------------------------------------------------- rendering
def meta_html(run):
    e = run["env"]
    auth = e.get("auth_mode", "none")
    return (f"<span>Run <b>{esc(run['name'])}</b></span><span>{esc(e.get('started', ''))} → {esc(e.get('finished', 'in progress'))}</span>"
            f"<span><b>{esc(e.get('vus', ''))}</b> constant VUs · warm-up <b>{esc(e.get('warmup', ''))}</b> · measured <b>{esc(e.get('duration', ''))}</b> · reps <b>{esc(e.get('reps', ''))}</b></span>"
            f"<span>Auth <b>{esc(auth)}</b>{' (HS256 JWT verified on every /readings request)' if auth == 'jwt' else ''}</span>"
            f"<span>App <b>{esc(e.get('app_cpus', ''))} vCPU / {esc(e.get('app_mem', ''))}</b> · PostgreSQL <b>{esc(e.get('db_cpus', ''))} vCPU / {esc(e.get('db_mem', ''))}</b></span>")


def render(run, pfx=""):
    """-> (nav links, html, facts). pfx namespaces element ids so several reports can share one page."""
    env, ran, order, wls, by = run["env"], run["ran"], run["order"], run["workloads"], run["by"]
    leaders = _leaders(run)
    geo = _geo_index(run, leaders)
    m = lambda s, wl, key: med(run, s, wl, key)
    i = lambda name: pfx + name

    # headline + findings
    findings = []
    for wl in wls:
        if len(leaders.get(wl, [])) >= 2:
            (a, av), (b, bv) = leaders[wl][:2]
            findings.append(f"<li><b>{esc(wl_name(wl))}</b>: {chip(a)} leads with <b>{fnum(av)}</b> req/s, {av / bv:.2f}× {esc(name_of(b))} ({fnum(bv)}).</li>")
    headline = ""
    if leaders.get("mixed"):
        mixed = leaders["mixed"]
        headline = (f'<p class="lede">Under the <b>mixed</b> workload (100 virtual users, {esc(env.get("duration", ""))}) <b>{esc(name_of(mixed[0][0]))}</b> '
                    f'delivered the highest throughput at <b>{fnum(mixed[0][1])}</b> successful requests/second.'
                    + (" Ranking: " + " &gt; ".join(f"{esc(name_of(s))} ({fnum(v)})" for s, v in mixed) + "." if len(mixed) > 1 else "") + "</p>")

    # summary table
    rows = []
    for wl in wls:
        ranks = {s: k for k, (s, _) in enumerate(leaders.get(wl, []))}
        row = [f"<b>{esc(wl_name(wl))}</b><br><small>{esc(WORKLOADS[wl][1])}</small>"]
        for s in ran:
            v = m(s, wl, "ok_rps")
            cls = ' class="best"' if ranks.get(s) == 0 else ""
            row.append("–" if v is None else
                       f"<span{cls}>{fnum(v)}</span> <small>req/s</small><br>"
                       f"<small>p95 {fms(m(s, wl, 'p95'))} ms · #{ranks.get(s, 0) + 1}</small>")
        rows.append(row)
    rows.append(["<b>Relative throughput index</b><br><small>geometric mean over workloads, best = 100 each</small>"]
                + [f"<b>{fnum(geo[s], 1)}</b>" if geo.get(s) else "–" for s in ran])
    summary_tbl = table(["Workload"] + [name_of(s) for s in ran], rows, "summary")
    cfg_tbl = table(["Stack", "Framework · runtime · driver", "DB connection pool (total 20)"],
                    [[chip(s), esc(STACKS.get(s, (s, "", 0, ""))[1]), esc(STACKS.get(s, (s, "", 0, ""))[3])] for s in order])

    def metric_grid(key, unit, digits, best="high"):
        cards = []
        for wl in wls:
            items = [(s, m(s, wl, key)) for s in ran]
            if any(v is not None for _, v in items):
                cards.append(hbar_card(wl_name(wl), WORKLOADS[wl][1], items, unit, digits, best))
        return grid(cards)

    # tables
    def per_cell(fn):
        return [fn(wl, s, cs) for wl in wls for s in ran for cs in [by.get((s, wl))] if cs]

    lat_tbl = table(["Workload", "Stack", "req/s", "avg ms", "p50", "p90", "p95", "p99", "max", "errors"], per_cell(
        lambda wl, s, cs: [esc(wl_name(wl)), chip(s), fnum(m(s, wl, "ok_rps")), fms(m(s, wl, "avg")), fms(m(s, wl, "p50")), fms(m(s, wl, "p90")),
                           fms(m(s, wl, "p95")), fms(m(s, wl, "p99")), fms(m(s, wl, "max")), f"{m(s, wl, 'fail_rate') * 100:.2f}%"]), "dense")
    res_tbl = table(["Workload", "Stack", "App CPU (cores of 2)", "App mem peak MiB", "DB CPU (cores of 2)", "DB mem MiB",
                     "req/s per app core", "bytes/response", "Limiting factor"], per_cell(
        lambda wl, s, cs: [esc(wl_name(wl)), chip(s), fnum(m(s, wl, "app_cpu"), 2), fnum(m(s, wl, "app_mem")), fnum(m(s, wl, "db_cpu"), 2),
                           fnum(m(s, wl, "db_mem")), fnum(m(s, wl, "rps_per_core")), fnum(m(s, wl, "bytes_per_req")), esc(cs[0]["bound"])]), "dense")

    rel_rows = []
    for s in order:
        info, sm = run["info"][s], run["smoke"][s]
        ins = read(os.path.join(run["dir"], "logs", f"inspect-{s}.txt")).split()
        rel_rows.append([chip(s), esc(STACKS.get(s, (s, ""))[1]), f"{info['build']} s", f"{info['startup']} s",
                         esc(read(os.path.join(run["dir"], "postgres", f"pgconns-{s}.txt")).strip() or "–"),
                         f"{sm['pass']} / {sm['pass'] + len(sm['fail'])}", esc({"pass": "pass", "fail": "FAIL"}.get(info["smoke"], info["smoke"])),
                         ("yes" if ins[0] == "true" else "no") if ins else "–", esc(ins[1]) if len(ins) > 1 else "–"])
    rel_tbl = table(["Stack", "Implementation", "Build + create", "Startup to healthy", "DB sessions", "Smoke checks passed", "Smoke", "OOM-killed", "Restarts"], rel_rows)
    fail_blocks = "".join(f"<h4>{esc(name_of(s))}: failed checks</h4><pre>{esc(chr(10).join(run['smoke'][s]['fail']))}</pre>" for s in ran if run["smoke"][s]["fail"])

    pg_blocks = ""
    for s in ran:
        c = (by.get((s, "mixed")) or by.get((s, wls[-1])) or [None])[0] if wls else None
        if c:
            pg_blocks += (f"<h4>{chip(s)} <small>{esc(wl_name(c['workload']))}</small></h4>"
                          f"<pre>calls | mean ms | total ms | statement\n{esc(c['pgstmt'] or 'no data')}</pre>")
    cache_rows = []
    for wl in wls:
        for s in ran:
            cs = by.get((s, wl))
            p = cs[0]["pgdb"].split("|") if cs and cs[0]["pgdb"] else []
            if len(p) < 6:
                continue
            try:
                hit, rd = int(p[0]), int(p[1])
                ratio = 100 * hit / (hit + rd) if hit + rd else 100
                cache_rows.append([esc(wl_name(wl)), chip(s), f"{ratio:.2f}%", fnum(int(p[2])), fnum(int(p[4])), esc(p[5]),
                                   f"{cs[0]['rows_before']:,} → {cs[0]['rows_after']:,}"])
            except ValueError:
                continue
    cache_tbl = table(["Workload", "Stack", "Buffer cache hit", "Commits", "Rows inserted", "Temp files", "readings rows (start → end)"], cache_rows, "dense")
    raw_tbl = table(["Workload", "Stack", "Rep", "Requests", "req/s", "p50 ms", "p95 ms", "p99 ms", "Failed", "Checks passed", "MB received", "k6 exit"], [
        [esc(c["workload"]), chip(c["stack"]), c["rep"], fnum(c["count"]), fnum(c["rps"], 1), fms(c["p50"]), fms(c["p95"]), fms(c["p99"]),
         f"{c['fail_rate'] * 100:.3f}%", f"{c['chk_pass']:,}/{c['chk_pass'] + c['chk_fail']:,}", f"{c['recv_mb']:.1f}", esc(c["k6_exit"])]
        for c in run["cells"]], "dense")

    stack_names = ", ".join(name_of(s) for s in order)
    links = [("summary", "Summary"), ("throughput", "Throughput"), ("latency", "Latency"), ("resources", "Resources"),
             ("reliability", "Reliability"), ("postgres", "PostgreSQL"), ("method", "Method"), ("appendix", "Raw data")]
    links = [(i(a), b) for a, b in links]
    body = f"""
<section id="{i('summary')}"><h2>Summary</h2>
<p class="sub">1,000 devices · 1,000,000 seeded readings · identical SQL, pool size (20 connections in total) and response bodies.</p>
{headline}{warn_box(_warnings(run))}{summary_tbl}
<h3>Findings</h3><ul class="find">{''.join(findings)}</ul>
<details><summary>Stack configuration</summary>{cfg_tbl}</details></section>

<section id="{i('throughput')}"><h2>Throughput</h2>
<p class="sub">Successful requests per second (failed requests excluded). Higher is better. Bold value = leader per workload.</p>
{legend(ran)}{metric_grid('ok_rps', ' req/s', 0)}</section>

<section id="{i('latency')}"><h2>Latency</h2>
<p class="sub">End-to-end request duration seen by k6, in milliseconds. Lower is better. Tail latency matters as much as the median.</p>
<h3>p50</h3>{metric_grid('p50', ' ms', 1, 'low')}<h3>p95</h3>{metric_grid('p95', ' ms', 1, 'low')}<h3>p99</h3>{metric_grid('p99', ' ms', 1, 'low')}
<details open><summary>Full latency table</summary>{lat_tbl}</details></section>

<section id="{i('resources')}"><h2>Resource usage</h2>
<p class="sub">Sampled from <code>docker stats</code> during the measured window (steady-state middle). CPU is in cores: the app limit is 2.0, so ≈2.0 means the container hit its CPU quota.</p>
<h3>App CPU (cores)</h3>{metric_grid('app_cpu', ' cores', 2, 'low')}
<h3>App memory peak (MiB, limit 4096)</h3>{metric_grid('app_mem', ' MiB', 0, 'low')}
<h3>Efficiency: successful requests per app CPU core</h3>{metric_grid('rps_per_core', ' req/s/core', 0)}
<h3>PostgreSQL CPU (cores of 2)</h3>{metric_grid('db_cpu', ' cores', 2, 'low')}
<details open><summary>Resource table with limiting factor</summary>{res_tbl}</details>
<p class="note"><b>Reading “limiting factor”:</b> <i>app CPU</i>: the application used ≥1.7 of its 2 cores, so the stack is the bottleneck. <i>database CPU</i>: PostgreSQL was saturated, so the result mostly measures the database. <i>latency-bound</i>: neither was saturated; with only 100 closed-loop users, throughput is then set by per-request latency. <i>load generator / network</i>: the app did not saturate on the no-DB health route, so k6 or the Docker network is the limit.</p></section>

<section id="{i('reliability')}"><h2>Reliability &amp; contract</h2>
<p class="sub">Each stack is checked against the same byte-exact contract (ground truth taken from PostgreSQL) before load is applied.</p>{rel_tbl}{fail_blocks}</section>

<section id="{i('postgres')}"><h2>PostgreSQL</h2>
<p class="sub">Per-statement cost from <code>pg_stat_statements</code> (mixed workload) and buffer-cache behaviour per run. The database is reset to the exact 1,000,000-row baseline and cache-primed before each measured run.</p>
{pg_blocks}<h3>Cache and write volume</h3>{cache_tbl}</section>

<section id="{i('method')}"><h2>Method and limitations</h2><div class="panel note"><ul>
<li><b>Closed workload model.</b> {esc(env.get('vus', '100'))} virtual users each send the next request as soon as the previous finishes (k6 <code>constant-vus</code>). It measures capacity for a fixed client population; it can hide behaviour under a fixed arrival rate (coordinated omission). The ramp test covers the open model.</li>
<li><b>Same everything except the stack.</b> Same PostgreSQL 17 instance (2 vCPU, 2 GiB), schema, index and seed, same six routes and JSON bodies, 20 database connections in total, no ORM, no cache, no compression, no TLS, HTTP/1.1 keep-alive.</li>
<li><b>Container limits.</b> Each app: 2 vCPU and 4 GiB. These are CFS quotas, not dedicated cores, and runtimes were told their CPU count (<code>GOMAXPROCS=2</code>, <code>ActiveProcessorCount=2</code>, 2 Node workers, 2 Tokio threads, 2 uvicorn workers, 20 PHP-FPM children, 4 Octane workers).</li>
<li><b>Environment grade: local.</b> One machine, inside a Docker Desktop VM ({esc(env.get('docker_vm_cpus', '?'))} vCPU, {esc(env.get('docker_vm_mem_gb', '?'))} GiB, {esc(env.get('docker_arch', ''))}): load generator, database and app share the host and the VM adds scheduling noise. Treat absolute numbers as indicative and ratios with care; publish-grade results need a dedicated Linux host with CPU pinning.</li>
<li><b>Short runs, few repetitions.</b> {esc(env.get('duration', ''))} measured after {esc(env.get('warmup', ''))} warm-up, {esc(env.get('reps', '1'))} repetition(s) per cell. JIT runtimes (JVM, V8) benefit from longer warm-up; one repetition gives no dispersion estimate.</li>
<li><b>Reset between workloads.</b> Before each warm-up and measured run the table is trimmed to the 1,000,000 seeded rows, VACUUMed, checkpointed, pre-warmed into shared buffers, and statistics are reset. Each app stays running across its workloads, in the same order for every stack.</li>
<li><b>Stack order.</b> Stacks ran sequentially in a fixed order ({esc(stack_names)}), not randomized, so slow thermal or background drift would affect them unevenly.</li>
<li><b>Resource sampling.</b> <code>docker stats</code> is coarse (about 1–2 s). The k6 container's own CPU is not sampled in this mode, so a client-side bottleneck cannot be fully ruled out on the fastest routes.</li>
<li><b>NestJS note.</b> JavaScript cannot distinguish <code>2375.0</code> from <code>2375</code>; only non-integer numbers are rejected as invalid.</li>
</ul></div></section>

<section id="{i('appendix')}"><h2>Raw data</h2>
<p class="sub">Every measured run. Source files (k6 summaries, docker stats samples, logs, smoke output) are in <code>{esc(run['dir'])}</code>.</p>{raw_tbl}</section>"""

    facts = {"ran": ran, "leaders": leaders, "geo": geo, "med": m, "warnings": len(_warnings(run))}
    return links, body, facts
