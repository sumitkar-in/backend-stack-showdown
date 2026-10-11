"""Shared metadata, parsers, SVG/HTML helpers and the one stylesheet used by every report (stdlib only)."""
import html
import json
import math
import os
import re
import statistics

# key -> (display name, implementation, colour slot, connection-pool layout)
STACKS = {
    "nest": ("NestJS", "Node 22 · Fastify · pg · 2 cluster workers", 1, "2 cluster workers × pool 10"),
    "spring": ("Spring Boot", "Java 21 · Tomcat MVC · JDBC · HikariCP", 2, "Hikari 20 (min = max)"),
    "graalvm": ("Spring Boot Native", "GraalVM native image · Tomcat MVC · JDBC · HikariCP", 8, "Hikari 20 (min = max)"),
    "go": ("Go", "Gin · pgx/v5 pgxpool", 3, "pgxpool 20 (min = max)"),
    "rust": ("Rust", "Axum 0.8 · Tokio · SQLx", 4, "SQLx 20 (min = max)"),
    "fastapi": ("FastAPI", "Uvicorn · asyncpg · 2 workers", 5, "2 workers × pool 10"),
    "laravel": ("Laravel", "PHP 8.3 · nginx + PHP-FPM · PDO pgsql", 6, "20 static PHP-FPM workers × 1 persistent connection"),
    "octane": ("Laravel Octane", "PHP 8.3 · Laravel Octane (Swoole) · PDO pgsql", 7, "4 Swoole workers × 1 connection"),
}
WORKLOADS = {
    "health": ("Health", "GET /health · no DB"),
    "pk": ("PK lookup", "GET /readings/{id}"),
    "range": ("Range list", "GET /readings?deviceId&from&to · 50 rows"),
    "stats": ("Aggregate", "GET /readings/stats · COUNT/SUM/MIN/MAX over 1,000 rows"),
    "insert": ("Single insert", "POST /readings"),
    "batch": ("Batch insert", "POST /readings/batch · 10 rows"),
    "mixed": ("Mixed", "50% pk · 30% range · 10% stats · 9% insert · 1% batch"),
}
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
RESULTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "results"))


def name_of(stack):
    return STACKS.get(stack, (stack,))[0]


def wl_name(wl):
    return WORKLOADS.get(wl, (wl, ""))[0]


# ---------------------------------------------------------------- files
def esc(s):
    return html.escape(str(s))


def read(path, default=""):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return default


def tsv(path):
    return [ln.split("\t") for ln in read(path).splitlines() if ln.strip()]


def kv(path):
    out = {}
    for ln in read(path).splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            out[k] = v
    return out


def jload(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def runs(kind, root=RESULTS):
    d = os.path.join(root, kind)
    return sorted((x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))), reverse=True) if os.path.isdir(d) else []


def metric(data, name):
    m = ((data or {}).get("metrics") or {}).get(name) or {}
    return m.get("values", m)


# ---------------------------------------------------------------- docker stats
def to_mib(txt):
    m = re.match(r"([\d.]+)\s*([KMGT]?i?B|kB)", txt.strip())
    if not m:
        return None
    scale = {"b": 1 / 1048576, "kb": 1 / 1024, "kib": 1 / 1024, "mib": 1, "mb": 1, "gib": 1024, "gb": 1024}
    return float(m.group(1)) * scale.get(m.group(2).lower(), 1)


def stats_samples(path):
    """Parse a docker-stats capture -> {'app': [(ts|None, cores, MiB)], 'db': [...]}.

    Lines are 'name|cpu%|mem / limit', optionally prefixed with an epoch timestamp (ramp runs)."""
    out = {"app": [], "db": []}
    for ln in ANSI.sub("", read(path)).splitlines():
        parts = ln.strip().split("|")
        if len(parts) != 3:
            continue
        head, cpu, mem = parts
        ts = None
        if " " in head.strip():
            first, head = head.strip().split(" ", 1)
            try:
                ts = float(first)
            except ValueError:
                continue
        try:
            cores = float(cpu.strip().rstrip("%")) / 100.0
        except ValueError:
            continue
        out["db" if "postgres" in head else "app"].append((ts, cores, to_mib(mem.split("/")[0])))
    return out


def steady_state(rows):
    """Mean/max CPU over the steady middle of a run, peak memory over all of it."""
    if len(rows) < 4:
        return None
    lo, hi = int(len(rows) * 0.15), int(len(rows) * 0.92)
    mid = rows[lo:hi] or rows
    return {"cpu": statistics.mean(r[1] for r in mid), "cpu_max": max(r[1] for r in mid),
            "mem_peak": max((r[2] or 0) for r in rows), "samples": len(rows)}


# ---------------------------------------------------------------- formatting
def fnum(v, digits=0):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    return f"{v:,.{digits}f}"


def fms(v, fine=False):
    """Milliseconds. fine=True keeps 2 decimals below 10 ms (sub-millisecond ramp results)."""
    if v is None:
        return "–"
    if fine and v < 10:
        return f"{v:.2f}"
    return f"{v:,.1f}" if v < 100 else f"{v:,.0f}"


def median(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


# ---------------------------------------------------------------- html pieces
def chip(stack):
    return f'<span class="chip s-{esc(stack)}"><i></i>{esc(name_of(stack))}</span>'


def table(headers, rows, cls=""):
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def grid(cards):
    return '<div class="grid">' + "".join(cards) + "</div>"


def legend(stacks):
    return '<div class="legend">' + "".join(chip(s) for s in stacks) + "</div>"


def warn_box(items, title="Validity notes"):
    if not items:
        return ""
    return f'<div class="warn"><b>{esc(title)}</b><ul>' + "".join(f"<li>{esc(w)}</li>" for w in items) + "</ul></div>"


def bar_path(x, y, w, h, r=4):
    r = min(r, h / 2, w)
    if w <= 0:
        return ""
    return (f"M{x:.1f},{y:.1f} h{w - r:.1f} a{r},{r} 0 0 1 {r},{r} v{h - 2 * r:.1f} "
            f"a{r},{r} 0 0 1 {-r},{r} h{-(w - r):.1f} z")


def hbar_card(title, sub, items, unit="", digits=0, best="high"):
    """items: [(stack, value|None)] -> one small horizontal-bar card (shared scale, value labels)."""
    vals = [v for _, v in items if v is not None]
    vmax = max(vals) if vals else 1
    lead = (max if best == "high" else min)(vals) if vals else None
    row_h, bar_x, bar_w, top = 30, 78, 190, 4
    h = top + row_h * len(items) + 4
    parts = [f'<svg viewBox="0 0 360 {h}" role="img" aria-label="{esc(title)}">']
    for i, (stack, v) in enumerate(items):
        y = top + i * row_h
        parts.append(f'<text x="0" y="{y + 15}" class="lbl">{esc(name_of(stack))}</text>')
        if v is None:
            parts.append(f'<text x="{bar_x}" y="{y + 15}" class="muted">no data</text>')
            continue
        w = max(2.0, bar_w * v / vmax) if vmax else 2
        tip = f"{name_of(stack)}: {fnum(v, digits)}{unit}"
        parts.append(f'<g class="bar s-{esc(stack)}"><title>{esc(tip)}</title><path d="{bar_path(bar_x, y + 3, w, 16)}"/></g>')
        parts.append(f'<text x="{bar_x + w + 6:.1f}" y="{y + 16}" class="val{" lead" if v == lead else ""}">'
                     f'{fnum(v, digits)}<tspan class="unit">{esc(unit)}</tspan></text>')
    parts.append("</svg>")
    return (f'<figure class="card"><figcaption><b>{esc(title)}</b><span>{esc(sub)}</span></figcaption>'
            + "".join(parts) + "</figure>")


# ---------------------------------------------------------------- page shell
_LIGHT = ("--bg:#f6f6f4;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--ink3:#7a7974;--line:#e4e3de;--grid:#ecebe7;--bad:#c4342d;--accent:#2a78d6;"
          "--warnbg:#fff4e0;--warnline:#e6a23c;--series-1:#2a78d6;--series-2:#eb6834;--series-3:#1baf7a;--series-4:#eda100;--series-5:#e87ba4;--series-6:#6250d6;--series-7:#0aa5b5;--series-8:#8a5a2b")
_DARK = ("--bg:#121211;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--ink3:#8f8e86;--line:#2e2e2b;--grid:#262624;--bad:#ff6b63;--accent:#3987e5;"
         "--warnbg:#2b2210;--warnline:#8a6a1f;--series-1:#3987e5;--series-2:#d95926;--series-3:#199e70;--series-4:#c98500;--series-5:#d55181;--series-6:#9085e9;--series-7:#2cc3d3;--series-8:#b88350")

CSS = (
    f":root{{color-scheme:light;{_LIGHT}}}\n"
    f"@media (prefers-color-scheme:dark){{:root:not([data-theme=\"light\"]){{color-scheme:dark;{_DARK}}}}}\n"
    f":root[data-theme=\"dark\"]{{color-scheme:dark;{_DARK}}}\n"
    + "".join(f".s-{k}{{--c:var(--series-{v[2]})}}" for k, v in STACKS.items()) + """
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
main{max-width:1120px;margin:0 auto;padding:32px 16px 80px}
h1{font-size:30px;line-height:1.15;margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:21px;margin:0 0 4px;letter-spacing:-.005em} h2+p.sub{margin:0 0 16px}
h3{font-size:16px;margin:28px 0 8px} h4{font-size:14px;margin:18px 0 6px}
.sub,header p{color:var(--ink2);margin:0 0 10px;font-size:14px} .muted,small{color:var(--ink3)}
.meta{display:flex;flex-wrap:wrap;gap:8px 20px;margin-top:14px;color:var(--ink2);font-size:13px} .meta b{color:var(--ink)}
nav{position:sticky;top:0;background:var(--bg);padding:10px 0;margin:18px 0 0;border-bottom:1px solid var(--line);z-index:5;display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px}
nav a{color:var(--ink2);text-decoration:none} nav a:hover{color:var(--ink);text-decoration:underline}
nav.sub-nav{position:static;border:0;padding:0;margin:6px 0 0}
section{margin-top:44px}
.part{margin-top:64px;padding-top:28px;border-top:2px solid var(--line)} .part>h1{font-size:26px}
.lede{font-size:17px;margin:16px 0} ul.find{padding-left:20px} ul.find li{margin:5px 0}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:6px 18px;color:var(--ink2)} .panel li{margin:5px 0}
.warn{background:var(--warnbg);border:1px solid var(--warnline);border-radius:10px;padding:10px 16px;margin:16px 0;font-size:14px} .warn ul{margin:6px 0 0;padding-left:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(480px,1fr));gap:14px}
.card{margin:0;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px 8px}
.card figcaption{display:flex;flex-direction:column;margin-bottom:6px} .card figcaption span{font-size:12px;color:var(--ink3)}
svg{width:100%;height:auto;display:block} svg text{font:12px -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;fill:var(--ink2)}
svg .val.lead{fill:var(--ink);font-weight:600} svg .unit,svg .muted,svg .axis{fill:var(--ink3);font-size:11px}
.bar path{fill:var(--c)} .bar:hover path{opacity:.8}
svg .gl{stroke:var(--grid);stroke-width:1} svg .ref{stroke:var(--bad);stroke-width:1.5;stroke-dasharray:5 4} svg .reftxt{fill:var(--bad)}
svg .line{fill:none;stroke:var(--c);stroke-width:2} svg .pt{fill:var(--c);stroke:var(--surface);stroke-width:2} svg .pt.bad{stroke:var(--bad);stroke-width:2.5}
.chip{display:inline-flex;align-items:center;gap:6px;white-space:nowrap} .chip i{width:10px;height:10px;border-radius:3px;background:var(--c);display:inline-block}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:0 0 14px;font-size:13px;color:var(--ink2)}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--ink2);font-size:12px;text-transform:uppercase;letter-spacing:.03em}
tr:last-child td{border-bottom:0}
table.dense td,table.dense th{padding:6px 10px;font-variant-numeric:tabular-nums} table.summary td,table.score td{font-variant-numeric:tabular-nums}
.best{font-weight:700;color:var(--ink)} .neg{color:var(--bad)} .pass{color:var(--ink)} .fail{color:var(--bad);font-weight:600}
details{margin-top:12px} summary{cursor:pointer;color:var(--ink2);font-size:13px}
pre{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 12px;overflow:auto;font-size:12px;line-height:1.45}
.note{color:var(--ink2)} .note li{margin:5px 0}
.runs{display:grid;gap:12px} .run{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 16px}
.run header{display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex-wrap:wrap}
a.open{color:var(--accent);text-decoration:none;font-weight:600} a.open:hover{text-decoration:underline}
dl{display:grid;grid-template-columns:max-content 1fr;gap:2px 16px;margin:8px 0 4px;font-size:13.5px} dt{color:var(--ink3)} dd{margin:0;color:var(--ink2)}
.path{margin:6px 0 0;font-size:12px;color:var(--ink3)} code{font-family:ui-monospace,Menlo,monospace}
footer{margin-top:50px;color:var(--ink3);font-size:12px}
@media (max-width:560px){main{padding:20px 16px 60px} h1{font-size:24px} .grid2{grid-template-columns:1fr} dl{grid-template-columns:1fr} dt{margin-top:6px}}
""")


def nav(links, cls=""):
    return f'<nav class="{cls}">' + "".join(f'<a href="#{esc(i)}">{esc(t)}</a>' for i, t in links) + "</nav>"


def page(title, body):
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f"<title>{esc(title)}</title>\n<style>\n{CSS}</style></head><body><main>\n{body}\n</main></body></html>")


def write(path, doc):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(doc)
    os.replace(tmp, path)
    return path
