"""Open-model ramp run (results/ramps/<run>): where each stack breaks and the highest load with p95 under a target."""
import math
import os
import statistics

from .common import (STACKS, chip, esc, fms, fnum, jload, kv, legend, name_of, read, stats_samples, table, tsv, wl_name)

THRESHOLDS = [0.5, 1, 2, 5, 10, 25, 50, 100]
ERR_LIMIT, ACHIEVED_LIMIT = 0.01, 0.95
DROP_LIMIT = 0.005   # tolerate start-of-step transients (<0.5% of the step's iterations)
RAMP_WL = {"health": "Health (no DB)"}


# ---------------------------------------------------------------- analysis
def _mean_in(samples, lo, hi, idx=1):
    w = [r[idx] for r in samples if r[0] is not None and lo <= r[0] <= hi and r[idx] is not None]
    return statistics.mean(w) if w else None


def analyse(cell, t0, target, start_offset=2.0):
    cell["target"] = target
    steps, secs = cell["steps"], cell["stepSeconds"]
    stats = stats_samples(cell["_stats"])
    k6 = stats_samples(cell["_stats"].replace("stats-", "stats-k6-"))["app"]
    for i, s in enumerate(steps):
        s["achieved"] = s["count"] / secs
        s["err_rate"] = (s["errors"] / s["count"]) if s["count"] else 1.0
        s["ok"] = (s["count"] > 0 and s["err_rate"] <= ERR_LIMIT and s["achieved"] >= ACHIEVED_LIMIT * s["offered"]
                   and s["dropped"] <= DROP_LIMIT * s["offered"] * secs)
        lo = t0 + start_offset + cell["warmSeconds"] + i * secs + 2   # skip first 2 s of each step
        hi = t0 + start_offset + cell["warmSeconds"] + (i + 1) * secs
        s["app_cpu"], s["db_cpu"], s["k6_cpu"] = _mean_in(stats["app"], lo, hi), _mean_in(stats["db"], lo, hi), _mean_in(k6, lo, hi)
        mem = [r[2] for r in stats["app"] if r[0] is not None and lo <= r[0] <= hi and r[2]]
        s["app_mem"] = max(mem) if mem else None
    last_ok = -1
    for i, s in enumerate(steps):          # contiguous healthy prefix = sustainable region
        if not s["ok"]:
            break
        last_ok = i
    cell["last_ok"] = last_ok
    cell["break_idx"] = last_ok + 1 if last_ok + 1 < len(steps) else None
    cell["thr"], cell["thr_lo"] = {}, {}
    for T in sorted(set(THRESHOLDS + [target])):
        # latency is U-shaped (idle CPU / cold paths make very low rates slower), so do not require the lowest steps to
        # pass; require only that the step and everything below it was healthy.
        hits = [i for i, s in enumerate(steps) if i <= last_ok and s["p95"] is not None and s["p95"] <= T]
        cell["thr"][T] = max(hits) if hits else None
        cell["thr_lo"][T] = min(hits) if hits else None
    return cell


def reason(s):
    if s["count"] == 0:
        return "no responses"
    r = []
    if s["err_rate"] > ERR_LIMIT:
        r.append(f"errors {s['err_rate'] * 100:.1f}%")
    if s["achieved"] < ACHIEVED_LIMIT * s["offered"]:
        r.append(f"served {s['achieved']:,.0f} of {s['offered']:,} req/s")
    if s["dropped"] > DROP_LIMIT * s["offered"] * s["seconds"]:
        r.append(f"{int(s['dropped']):,} dropped iterations")
    return ", ".join(r) or "ok"


def limiter(s, k6_cpus):
    if s is None:
        return "–"
    if s.get("app_cpu") is not None and s["app_cpu"] >= 1.7:
        return "app CPU (2 vCPU quota)"
    if s.get("db_cpu") is not None and s["db_cpu"] >= 1.7:
        return "database CPU"
    if s.get("k6_cpu") is not None and s["k6_cpu"] >= 0.8 * k6_cpus:
        return "load generator CPU (k6)"
    return "load generator VU cap / network"


def load(out):
    env = kv(os.path.join(out, "env.txt"))
    target = float(env.get("p95_target_ms", "0.5"))
    by_wl = {}
    for r in tsv(os.path.join(out, "cells.tsv")):
        stack, wl, t0 = r[0], r[1], r[2]
        c = jload(os.path.join(out, "k6", f"{stack}-{wl}.json"))
        if not c:
            continue
        c["_stats"] = os.path.join(out, "stats", f"stats-{stack}-{wl}.raw")
        c["k6_exit"] = r[3]
        by_wl.setdefault(wl, []).append((stack, analyse(c, float(t0), target)))
    for cells in by_wl.values():
        cells.sort(key=lambda x: STACKS.get(x[0], ("", "", 99))[2])
    return {"dir": out, "name": os.path.basename(out), "env": env, "target": target, "k6_cpus": float(env.get("k6_cpus", "4")),
            "by_wl": by_wl, "stacks": sorted({s for cells in by_wl.values() for s, _ in cells}, key=lambda s: STACKS.get(s, ("", "", 99))[2])}


# ---------------------------------------------------------------- charts
def line_chart(title, cells, ykey, ylog, ylabel, ref=None, yfmt=lambda v: f"{v:g}"):
    """x = ramp steps (offered req/s, evenly spaced); one line per stack; optional horizontal reference."""
    W, H, ml, mr, mt, mb = 760, 330, 56, 18, 14, 54
    rates = cells[0][1]["steps"] if cells else []
    n = len(rates)
    vals = [s[ykey] for _, c in cells for s in c["steps"] if s[ykey] is not None and (s[ykey] != 0 or not ylog)]
    if not vals or not n:
        return ""
    lo, hi = min(vals + ([ref] if ref else [])), max(vals + ([ref] if ref else []))
    if ylog:
        lo, hi = 10 ** math.floor(math.log10(lo)), 10 ** math.ceil(math.log10(hi))
        f = lambda v: (math.log10(max(v, lo)) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
        ticks = [10 ** k for k in range(int(math.log10(lo)), int(math.log10(hi)) + 1)]
    else:
        lo = 0
        hi = max(hi * 1.08, 0.01 if ykey == "err_rate" else 1e-6)
        f = lambda v: (v - lo) / (hi - lo)
        step = 10 ** math.floor(math.log10(hi))
        ticks = [step * k for k in range(0, int(hi / step) + 1)]
    px = lambda i: ml + (W - ml - mr) * (i / max(1, n - 1))
    py = lambda v: mt + (H - mt - mb) * (1 - f(v))
    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(title)}">']
    for t in ticks:
        y = py(t)
        p.append(f'<line x1="{ml}" x2="{W - mr}" y1="{y:.1f}" y2="{y:.1f}" class="gl"/>'
                 f'<text x="{ml - 8}" y="{y + 4:.1f}" text-anchor="end">{esc(yfmt(t))}</text>')
    for i, s in enumerate(rates):
        k = s["offered"]
        p.append(f'<text x="{px(i):.1f}" y="{H - mb + 18}" text-anchor="middle">{f"{k / 1000:g}k" if k >= 1000 else k}</text>')
    p.append(f'<text x="{(ml + W - mr) / 2}" y="{H - 8}" text-anchor="middle" class="axis">offered load (req/s)</text>')
    p.append(f'<text x="12" y="{mt + 4}" class="axis">{esc(ylabel)}</text>')
    if ref:
        y = py(ref)
        p.append(f'<line x1="{ml}" x2="{W - mr}" y1="{y:.1f}" y2="{y:.1f}" class="ref"/>'
                 f'<text x="{W - mr}" y="{y - 5:.1f}" text-anchor="end" class="reftxt">target {ref:g} ms</text>')
    for st, c in cells:
        pts = [(px(i), py(s[ykey])) for i, s in enumerate(c["steps"]) if s[ykey] is not None and (s[ykey] > 0 or not ylog)]
        if not pts:
            continue
        d = " ".join(f"{'M' if j == 0 else 'L'}{x:.1f},{y:.1f}" for j, (x, y) in enumerate(pts))
        p.append(f'<g class="s-{st}"><path d="{d}" class="line"/>')
        for i, s in enumerate(c["steps"]):
            if s[ykey] is None or (ylog and s[ykey] <= 0):
                continue
            bad = not s["ok"]
            p.append(f'<circle cx="{px(i):.1f}" cy="{py(s[ykey]):.1f}" r="{4.5 if bad else 3}" class="pt{" bad" if bad else ""}">'
                     f'<title>{esc(name_of(st))} @ {s["offered"]:,} req/s: {esc(yfmt(s[ykey]))}'
                     f'{" – BROKEN: " + esc(reason(s)) if bad else ""}</title></circle>')
        p.append("</g>")
    p.append("</svg>")
    return f'<figure class="card"><figcaption><b>{esc(title)}</b></figcaption>{"".join(p)}</figure>'


# ---------------------------------------------------------------- rendering
def meta_html(run):
    e = run["env"]
    return (f"<span>Run <b>{esc(run['name'])}</b></span><span>{esc(e.get('started', ''))} → {esc(e.get('finished', ''))}</span>"
            f"<span>Steps <b>{esc(e.get('rates', ''))}</b> req/s × <b>{esc(e.get('step_dur', ''))} s</b></span>"
            f"<span>App <b>2 vCPU / 4 GiB</b> · PostgreSQL 2 vCPU / 2 GiB · max <b>{esc(e.get('max_vus', ''))}</b> k6 VUs</span>"
            f"<span>Docker VM {esc(e.get('docker_vm_cpus', '?'))} vCPU / {esc(e.get('docker_vm_mem_gb', '?'))} GiB</span>")


def facts_of(run):
    """{workload: {stack: {...}}} for the combined overview."""
    out, target = {}, run["target"]
    for wl, cells in run["by_wl"].items():
        out[wl] = {}
        for st, c in cells:
            steps = c["steps"]
            ok = steps[c["last_ok"]] if c["last_ok"] >= 0 else None
            br = steps[c["break_idx"]] if c["break_idx"] is not None else None
            t = steps[c["thr"][target]] if c["thr"].get(target) is not None else None
            out[wl][st] = {"max_ok": ok["offered"] if ok else None, "target_load": t["offered"] if t else None,
                           "breaks_at": br["offered"] if br else None, "limiter": limiter(br or ok, run["k6_cpus"]),
                           "lowest_p95": steps[0]["p95"]}
    return out


def render(run, pfx=""):
    target, k6_cpus = run["target"], run["k6_cpus"]
    thresholds = sorted(set(THRESHOLDS + [target]))
    sections, findings, links = [], {}, []
    for wl, cells in run["by_wl"].items():
        rows = []
        for st, c in cells:
            steps = c["steps"]
            ok_s = steps[c["last_ok"]] if c["last_ok"] >= 0 else None
            br = steps[c["break_idx"]] if c["break_idx"] is not None else None
            ti = c["thr"].get(target)
            tstep = steps[ti] if ti is not None else None
            rows.append([
                chip(st),
                (f"<b>{fnum(tstep['offered'])}</b> req/s <small>p95 {fms(tstep['p95'], True)} ms; holds from {steps[c['thr_lo'][target]]['offered']:,} req/s</small>" if tstep else
                 f"<b>never</b> <small>lowest step p95 {fms(steps[0]['p95'], True)} ms @ {steps[0]['offered']:,}</small>"),
                (f"<b>{fnum(ok_s['offered'])}</b> req/s <small>p95 {fms(ok_s['p95'], True)} ms</small>" if ok_s else "<b>none</b>"),
                (f"{fnum(br['offered'])} req/s <small>{esc(reason(br))}</small>" if br else "not reached <small>(raise RATES)</small>"),
                esc(limiter(br or ok_s, k6_cpus)),
                f"{ok_s['app_cpu']:.2f}" if ok_s and ok_s.get("app_cpu") is not None else "–",
            ])
            if tstep:
                findings.setdefault(wl, []).append((tstep["offered"], st))
        head = table(["Stack", f"Max load with p95 ≤ {target:g} ms", "Max healthy load (any latency)", "Breaks at", "Limiting factor",
                      "App CPU at max healthy (of 2)"], rows)

        trows = []
        for T in thresholds:
            best = max((c["thr"][T] if c["thr"].get(T) is not None else -1 for _, c in cells), default=-1)
            r = [f"<b>p95 ≤ {T:g} ms</b>" + (" <small>(requested)</small>" if T == target else "")]
            for _, c in cells:
                idx = c["thr"].get(T)
                r.append("<span class='muted'>not reached</span>" if idx is None else
                         f"<span class='{'best' if idx == best else ''}'>{c['steps'][idx]['offered']:,}</span> <small>req/s</small>")
            trows.append(r)
        ladder = table(["Latency threshold"] + [name_of(s) for s, _ in cells], trows, "ladder")

        charts = (line_chart(f"p95 latency vs offered load: {RAMP_WL.get(wl, wl_name(wl))}", cells, "p95", True, "p95 (ms, log scale)", target)
                  + line_chart("Achieved throughput vs offered load", cells, "achieved", False, "served req/s", None, lambda v: f"{v:,.0f}")
                  + line_chart("Error rate", cells, "err_rate", False, "fraction of requests", None, lambda v: f"{v * 100:.1f}%")
                  + line_chart("App CPU (cores of 2.0)", cells, "app_cpu", False, "cores", None, lambda v: f"{v:.1f}"))
        detail = table(["Stack", "Offered", "Served", "p50 ms", "p90", "p95", "p99", "max", "Errors", "Dropped", "App CPU", "DB CPU", "k6 CPU", "State"], [
            [chip(st), f"{s['offered']:,}", f"{s['achieved']:,.0f}", fms(s["p50"], True), fms(s["p90"], True), fms(s["p95"], True), fms(s["p99"], True),
             fms(s["max"], True), f"{s['err_rate'] * 100:.2f}%", f"{int(s['dropped']):,}", fnum(s.get("app_cpu"), 2), fnum(s.get("db_cpu"), 2),
             fnum(s.get("k6_cpu"), 2), "ok" if s["ok"] else "<b>BROKEN</b> <small>" + esc(reason(s)) + "</small>"]
            for st, c in cells for s in c["steps"]], "dense")
        sid = f"{pfx}wl-{wl}"
        links.append((sid, RAMP_WL.get(wl, wl_name(wl))))
        sections.append(f"""<section id="{sid}"><h2>{esc(RAMP_WL.get(wl, wl_name(wl)))}</h2>
<h3>Where it breaks and the p95 ≤ {target:g} ms threshold</h3>{head}
<h3>Highest sustainable load per latency threshold</h3>
<p class="sub">Highest offered rate whose p95 stayed within the threshold, counting only steps where that step and every lower step were healthy.</p>{ladder}
<h3>Curves</h3>{legend([s for s, _ in cells])}<div class="grid2">{charts}</div>
<details><summary>All steps</summary>{detail}</details></section>""")

    if findings:
        lines = "".join(f"<li><b>{esc(RAMP_WL.get(wl, wl_name(wl)))}</b>: " + ", ".join(f"{chip(st)} {off:,} req/s" for off, st in sorted(lst, reverse=True)) + "</li>"
                        for wl, lst in findings.items())
        lede = f"<p class='lede'>Highest offered load that kept <b>p95 ≤ {target:g} ms</b> (healthy steps only):</p><ul class='find'>{lines}</ul>"
    else:
        lede = (f"<p class='lede'>No stack kept <b>p95 ≤ {target:g} ms</b> even at the lowest offered rate. Through k6 and the Docker network a sub-millisecond p95 "
                f"is usually out of reach; see the ladder below for the thresholds that were met.</p>")
    answer = f"""<section id="{pfx}answer"><h2>Answer</h2>{lede}
<div class="panel"><ul>
<li><b>Healthy step</b>: errors ≤ {ERR_LIMIT * 100:g}%, served ≥ {ACHIEVED_LIMIT * 100:g}% of the offered rate and dropped iterations ≤ {DROP_LIMIT * 100:g}%. The first step that fails this is where the stack <b>breaks</b>.</li>
<li><b>Threshold</b>: the highest healthy step whose p95 (client-side, including the Docker bridge and k6) stays within the limit. Very low rates are often slower than moderate ones (idle CPUs, cold paths), so the table also shows from which rate the stack first meets the limit.</li>
<li><b>Caveats</b>: everything runs on one machine, so the load generator competes for CPU. “Load generator VU cap / network” as the limiting factor means the app and database were not CPU-saturated and k6 (its CPU, or its {esc(run['env'].get('max_vus', ''))}-VU cap) probably limited the step. Latency below ~1 ms is near the floor of what k6 and Docker networking can resolve.</li></ul></div></section>"""
    return [(f"{pfx}answer", "Answer")] + links, answer + "".join(sections), facts_of(run)
