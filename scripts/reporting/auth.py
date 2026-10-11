"""JWT auth: contract results (results/auth/<run>/summary.md) and the throughput cost (no-auth vs jwt benchmark runs)."""
import os

from .common import RESULTS, STACKS, chip, esc, jload, kv, metric, name_of, read, runs, table, wl_name


# ---------------------------------------------------------------- contract results
def contract_rows(run_dir):
    """summary.md table -> {stack: (auth, api_with_token, auth_off, passed)}"""
    out = {}
    for ln in read(os.path.join(run_dir, "summary.md")).splitlines():
        cols = [c.strip() for c in ln.strip().strip("|").split("|")]
        if ln.startswith("|") and len(cols) >= 4 and cols[0] != "Stack" and not set(cols[0]) <= set("-: "):
            out[cols[0]] = (cols[1], cols[2], cols[3], all(c.startswith("PASS") for c in cols[1:4]))
    return out


def contract_latest(root=RESULTS):
    """Newest result per stack across every auth run (a later run can add a stack)."""
    merged = {}
    for name in sorted(runs("auth", root)):                        # oldest first so newer overwrite
        for stack, row in contract_rows(os.path.join(root, "auth", name)).items():
            merged[stack] = row + (name,)
    return merged


# ---------------------------------------------------------------- overhead
def _cell(run, stack, wl):
    d = jload(os.path.join(run, "k6", f"{stack}-{wl}-r1.json"))
    if not d:
        return None
    dur, reqs = metric(d, "http_req_duration"), metric(d, "http_reqs")
    return {"rps": reqs["rate"], "p95": dur["p(95)"]} if reqs and dur else None


def overhead(base, jwt):
    eb, ej = kv(os.path.join(base, "env.txt")), kv(os.path.join(jwt, "env.txt"))
    stacks = [s for s in ej.get("stacks", "").split() if s in eb.get("stacks", "").split()]
    wls = [w for w in ej.get("workloads", "").split() if w in eb.get("workloads", "").split()]
    rows = []
    for w in wls:
        for s in stacks:
            a, b = _cell(base, s, w), _cell(jwt, s, w)
            if a and b:
                rows.append({"workload": w, "stack": s, "base": a, "jwt": b, "change": (b["rps"] / a["rps"] - 1) * 100})
    return rows


def find_pair(root=RESULTS):
    """(no-auth run dir, jwt run dir): newest jwt benchmark and the newest no-auth run covering at least its workloads."""
    names = runs("benchmarks", root)
    envs = {n: kv(os.path.join(root, "benchmarks", n, "env.txt")) for n in names}
    for j in names:
        if envs[j].get("auth_mode") != "jwt":
            continue
        for b in names:
            if envs[b].get("auth_mode", "none") == "none" and set(envs[j].get("workloads", "").split()) <= set(envs[b].get("workloads", "").split()):
                if set(envs[j].get("stacks", "").split()) & set(envs[b].get("stacks", "").split()):
                    # prefer a run made for the comparison (same workload list) over the big all-stacks run
                    same = [x for x in names if envs[x].get("auth_mode", "none") == "none" and envs[x].get("workloads") == envs[j].get("workloads")]
                    pick = same[0] if same else b
                    return os.path.join(root, "benchmarks", pick), os.path.join(root, "benchmarks", j)
    return None


def overhead_median(rows):
    out = {}
    for s in {r["stack"] for r in rows}:
        v = sorted(r["change"] for r in rows if r["stack"] == s)
        out[s] = v[len(v) // 2]
    return out


# ---------------------------------------------------------------- rendering
def render(contract, pair, pfx=""):
    """-> (nav links, html, facts). contract: contract_latest(); pair: (base_dir, jwt_dir) | None"""
    links, parts = [], []
    if contract:
        rows = [[chip(s), esc(a), esc(b), esc(c), f"<span class='{'pass' if ok else 'fail'}'>{'PASS' if ok else 'FAIL'}</span>", f"<small>{esc(run)}</small>"]
                for s, (a, b, c, ok, run) in sorted(contract.items(), key=lambda kv_: STACKS.get(kv_[0], ("", "", 99))[2])]
        parts.append(f"""<section id="{pfx}contract"><h2>Auth contract</h2>
<p class="sub">HS256 bearer token on every <code>/readings</code> route; <code>/health</code> stays public. 29 auth checks (missing / malformed / expired / wrong-secret / <code>alg: none</code> / RS256 confusion, auth before validation and body parsing), the 38-check API contract with a valid token, and a check that <code>AUTH_MODE=none</code> needs no token.</p>
{table(["Stack", "Auth contract", "API contract with token", "Auth off needs no token", "Result", "Run"], rows)}</section>""")
        links.append((pfx + "contract", "Auth contract"))
    medians = {}
    if pair:
        rows = overhead(*pair)
        medians = overhead_median(rows)
        trs = [[esc(wl_name(r["workload"])), chip(r["stack"]), fnum0(r["base"]["rps"]), fnum0(r["jwt"]["rps"]),
                f"<b class='{'neg' if r['change'] < -2 else ''}'>{r['change']:+.1f}%</b>", f"{r['base']['p95']:.1f}", f"{r['jwt']['p95']:.1f}"] for r in rows]
        summ = ", ".join(f"{esc(name_of(s))} {v:+.1f}%" for s, v in sorted(medians.items(), key=lambda kv_: STACKS.get(kv_[0], ("", "", 99))[2]))
        parts.append(f"""<section id="{pfx}overhead"><h2>Cost of JWT authentication</h2>
<p class="sub">Same stacks, workloads and machine: <b>{esc(os.path.basename(pair[0]))}</b> (no auth) vs <b>{esc(os.path.basename(pair[1]))}</b> (HS256 verified on every request, never cached). One 30 s run per cell.</p>
<p>Median throughput change per stack: {summ}.</p>
<div class="panel"><ul><li><b>Caution.</b> On a laptop, run-to-run variance between sessions is large (20–40 %), so only big, consistent gaps mean anything. A back-to-back A/B (2 runs per mode, 15 s, same session) of Rust and Go PK lookups showed JWT costing 0–9 %, far less than the single-run gaps below.</li></ul></div>
{table(["Workload", "Stack", "no auth req/s", "JWT req/s", "change", "p95 no auth (ms)", "p95 JWT (ms)"], trs, "dense")}</section>""")
        links.append((pfx + "overhead", "JWT overhead"))
    if not parts:
        parts.append(f'<section id="{pfx}contract"><h2>Auth</h2><p class="muted">No auth runs yet. Run <code>scripts/run-auth-test.sh</code>.</p></section>')
    return links, "".join(parts), {"contract": contract, "overhead": medians, "rows": overhead(*pair) if pair else []}


def fnum0(v):
    return f"{v:,.0f}"
