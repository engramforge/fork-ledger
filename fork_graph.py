#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 EngramForge, Inc.
"""fork_graph.py — render a fork ledger as a scrolling commit-style graph.

Reads the ledger JSON and writes one self-contained HTML page: a lane per
arc, a node per fork in date order, curved edges for dependencies, cycle
detection, and the revisit condition inline on every card.

    python3 fork_graph.py [--ledger fork_ledger.json] [-o fork-graph.html]

Keep this file next to fork_ledger.py; it reuses that module's state rules
so the graph and the `wake` command can never disagree.
"""
from __future__ import annotations
import argparse, json, html
from datetime import date
from pathlib import Path

from fork_ledger import derived_state, is_unscheduled_text, ledger_path

ROW, LANE_W, LEFT, RAIL = 168, 30, 26, 380

# Lanes take colours from this palette in order of first appearance.
PALETTE = ["#f0576f", "#38bdf8", "#34d399", "#fbbf24", "#c084fc", "#818cf8",
           "#2dd4bf", "#f472b6", "#a3e635", "#94a3b8"]
MISC = "#64748b"
ARC_COLOR: dict[str, str] = {}

STATE = {  # (label, color) — derived state, most urgent wins
    "active":      ("IN FLIGHT",   "#fbbf24"),
    "fired":       ("READY",       "#34d399"),
    "orphaned":    ("ORPHANED",    "#f0576f"),
    "unscheduled": ("UNSCHEDULED", "#c084fc"),
    "pending":     ("PARKED",      "#475569"),
    "done":        ("RESOLVED",    "#334155"),
}


def state_of(f):
    return {"resolved": "done", "parked": "pending"}.get(derived_state(f), derived_state(f))


def find_cycles(forks):
    g = {f["id"]: f.get("depends_on", []) for f in forks}
    cycles, seen = [], set()
    def dfs(n, path, vis):
        if n in path:
            cyc = path[path.index(n):] + [n]
            key = tuple(sorted(set(cyc)))
            if key not in seen: seen.add(key); cycles.append(cyc)
            return
        if n in vis: return
        vis.add(n)
        for m in g.get(n, []): dfs(m, path + [n], vis)
    for n in g: dfs(n, [], set())
    return cycles


def build(data, out: Path):
    forks = sorted(data["forks"], key=lambda f: (f.get("opened", ""), f["id"]))
    arcs, lane = [], {}
    for f in forks:
        a = f.get("arc", "misc")
        if a not in lane:
            lane[a] = len(arcs); arcs.append(a)
            ARC_COLOR[a] = MISC if a == "misc" else PALETTE[(len(ARC_COLOR)) % len(PALETTE)]
    pos = {f["id"]: (LEFT + lane[f.get("arc", "misc")] * LANE_W, i * ROW + ROW // 2)
           for i, f in enumerate(forks)}
    cycles = find_cycles(forks)
    in_cycle = {i for c in cycles for i in c}
    H = len(forks) * ROW + 40

    # ---- SVG rail ----------------------------------------------------------
    svg = [f'<svg class="rail" width="{RAIL}" height="{H}" viewBox="0 0 {RAIL} {H}">']
    for a, li in lane.items():  # lane spines
        x = LEFT + li * LANE_W
        ys = [pos[f["id"]][1] for f in forks if f.get("arc", "misc") == a]
        if ys:
            svg.append(f'<line x1="{x}" y1="{min(ys)}" x2="{x}" y2="{max(ys)}" '
                       f'stroke="{ARC_COLOR.get(a,"#64748b")}" stroke-width="2" opacity=".28"/>')
    for f in forks:  # dependency curves
        x2, y2 = pos[f["id"]]
        for dep in f.get("depends_on", []):
            if dep not in pos: continue
            x1, y1 = pos[dep]
            cyc = f["id"] in in_cycle and dep in in_cycle
            col = "#f0576f" if cyc else ARC_COLOR.get(f.get("arc", "misc"), "#64748b")
            bow = max(46, abs(x2 - x1) * 1.7)
            dash = 'stroke-dasharray="7 4"' if cyc else ""
            svg.append(
                f'<path d="M {x1} {y1} C {x1+bow} {y1}, {x2+bow} {y2}, {x2} {y2}" fill="none" '
                f'stroke="{col}" stroke-width="{2.4 if cyc else 1.5}" opacity="{.95 if cyc else .5}" '
                f'{dash}/>')
    for f in forks:  # nodes
        x, y = pos[f["id"]]
        st = state_of(f); col = STATE[st][1]
        req = f.get("thesis_dep") == "REQUIRED"
        if req:
            svg.append(f'<circle cx="{x}" cy="{y}" r="11" fill="none" stroke="{col}" stroke-width="1.5" opacity=".55"/>')
        svg.append(f'<circle class="node" id="n-{f["id"]}" cx="{x}" cy="{y}" r="6.5" fill="{col}" '
                   f'stroke="#0b1220" stroke-width="2.5"/>')
    svg.append("</svg>")

    # ---- cards -------------------------------------------------------------
    cards = []
    for f in forks:
        st = state_of(f); label, col = STATE[st]
        e = lambda k: html.escape(str(f.get(k, "") or ""))
        deps = " ".join(f'<a href="#c-{d}" class="dep">{d}</a>' for d in f.get("depends_on", []))
        cyc = ' <span class="cyc">◉ IN CYCLE</span>' if f["id"] in in_cycle else ""
        req = ' <span class="req">thesis-required</span>' if f.get("thesis_dep") == "REQUIRED" else ""
        trig = ""
        if not is_unscheduled_text(f.get("trigger")):
            trig = (f'<div class="trig {st}"><span class="tl">revisit when</span>'
                    f'<span class="tt">{e("trigger")}</span>'
                    f'<span class="ts">{e("trigger_status")}</span></div>')
        elif st == "unscheduled":
            trig = ('<div class="trig unscheduled"><span class="tl">revisit when</span>'
                    '<span class="tt">— no condition recorded; surfaces only if someone looks —</span></div>')
        res = ""
        if f.get("closed_by") or f.get("superseded_by"):
            res = f'<div class="res">resolved by: {html.escape(f.get("closed_by") or f.get("superseded_by"))}</div>'
        cards.append(f'''
<article class="card {st}" id="c-{f["id"]}" style="--arc:{ARC_COLOR.get(f.get("arc","misc"),"#64748b")}">
  <header><span class="id">{f["id"]}</span><span class="pill" style="--c:{col}">{label}</span>
    <span class="arc">{e("arc")}</span>{req}{cyc}</header>
  <h3>{e("title")}</h3>
  <p class="sum">{e("summary")}</p>
  {f'<p class="why"><b>parked because:</b> {e("parked_because")}</p>' if f.get("parked_because") else ""}
  {trig}{res}
  <footer>opened {e("opened")} · {e("kind")} · owner {e("owner")} · cost {e("cost")}
    {f' · needs {deps}' if deps else ""}<span class="src">{e("source")}</span></footer>
</article>''')

    counts = {k: sum(1 for f in forks if state_of(f) == k) for k in STATE}
    cyc_html = ""
    if cycles:
        rows = []
        for c in cycles:
            byid = {f["id"]: f for f in forks}
            chain = " → ".join(f'<a href="#c-{i}">{i}</a>' for i in c)
            names = " ↔ ".join(html.escape(byid[i]["title"].split("—")[0].strip()) for i in c[:-1])
            rows.append(f'<div class="cyc-row"><div class="chain">{chain}</div><div class="names">{names}</div></div>')
        cyc_html = f'''<section class="cycles"><h2>◉ Circular dependency detected</h2>
<p>Each of these needs the other to have happened first. Nothing in the ledger breaks the loop —
it has to be broken by decision, by building one side on partial evidence.</p>{"".join(rows)}</section>'''

    legend = "".join(f'<span class="lg"><i style="background:{c}"></i>{l}</span>' for l, c in STATE.values())
    lanes_legend = "".join(f'<span class="lg"><i style="background:{ARC_COLOR.get(a,"#64748b")}"></i>{a}</span>' for a in arcs)

    doc = f'''<!doctype html><html><head><meta charset="utf-8">
<title>Fork Ledger — the paths not taken</title><style>
:root{{--bg:#0b1220;--fg:#e2e8f0;--dim:#94a3b8;--line:#1e293b;--card:#0f172a}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);
 font:14px/1.55 ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace}}
header.top{{position:sticky;top:0;z-index:20;background:rgba(11,18,32,.94);
 backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:14px 26px}}
header.top h1{{margin:0;font-size:17px;letter-spacing:.02em;font-weight:600}}
header.top p{{margin:5px 0 9px;color:var(--dim);font-size:12.5px;max-width:78ch}}
.legend{{display:flex;flex-wrap:wrap;gap:14px;font-size:11px;color:var(--dim)}}
.lg{{display:flex;align-items:center;gap:5px}}
.lg i{{width:9px;height:9px;border-radius:50%;display:inline-block}}
.cycles{{margin:20px 26px;padding:16px 20px;border:1px solid #f0576f55;
 border-left:3px solid #f0576f;background:#f0576f0d;border-radius:6px}}
.cycles h2{{margin:0 0 6px;font-size:14px;color:#f0576f;letter-spacing:.04em}}
.cycles p{{margin:0 0 12px;color:var(--dim);font-size:12.5px;max-width:80ch}}
.cyc-row{{padding:8px 0;border-top:1px solid #f0576f22}}
.chain a{{color:#f0576f;text-decoration:none;font-weight:600}}
.names{{color:var(--dim);font-size:12px;margin-top:3px}}
.wrap{{position:relative;display:flex;padding:0 26px 90px}}
.rail{{flex:0 0 {RAIL}px;position:sticky;top:0;align-self:flex-start;margin-top:0}}
.cards{{flex:1;min-width:0}}
.card{{height:{ROW}px;padding:12px 18px;margin:0;border-left:2px solid var(--arc);
 border-bottom:1px solid var(--line);background:linear-gradient(90deg,#ffffff05,transparent 60%);
 overflow:hidden;transition:background .15s}}
.card:target,.card:hover{{background:linear-gradient(90deg,#ffffff0d,transparent 70%)}}
.card header{{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:3px}}
.id{{color:var(--dim);font-size:11.5px;letter-spacing:.05em}}
.pill{{font-size:9.5px;letter-spacing:.09em;padding:2px 7px;border-radius:3px;
 background:color-mix(in srgb,var(--c) 17%,transparent);color:var(--c);border:1px solid color-mix(in srgb,var(--c) 42%,transparent)}}
.arc{{font-size:10.5px;color:var(--arc);opacity:.85}}
.req{{font-size:9.5px;letter-spacing:.07em;color:#f0576f;border:1px solid #f0576f4d;padding:1px 6px;border-radius:3px}}
.cyc{{font-size:9.5px;color:#f0576f;letter-spacing:.06em}}
.card h3{{margin:0 0 4px;font-size:13.5px;font-weight:600;line-height:1.35}}
.sum{{margin:0;color:var(--dim);font-size:12px;line-height:1.45;
 display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.why{{margin:4px 0 0;font-size:11.5px;color:#64748b}}
.why b{{color:#94a3b8;font-weight:500}}
.trig{{margin-top:5px;font-size:11.5px;display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}}
.tl{{color:#475569;font-size:10px;letter-spacing:.08em;text-transform:uppercase}}
.tt{{color:#cbd5e1}}
.ts{{font-size:9.5px;letter-spacing:.06em;color:#64748b}}
.trig.fired .tt{{color:#34d399}} .trig.orphaned .tt{{color:#f0576f;text-decoration:line-through}}
.trig.unscheduled .tt{{color:#c084fc}}
.res{{margin-top:5px;font-size:11.5px;color:#475569}}
.card footer{{margin-top:6px;font-size:10.5px;color:#475569;display:flex;gap:8px;flex-wrap:wrap}}
.src{{margin-left:auto;opacity:.6;max-width:44ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.dep{{color:#38bdf8;text-decoration:none}} .dep:hover{{text-decoration:underline}}
.card.done{{opacity:.42}}
</style></head><body>
<header class="top">
<h1>Fork Ledger — the paths not taken</h1>
<p>{len(forks)} forks across {len(arcs)} arcs. Every node is a decision point where one branch got
walked and another got parked. Ringed nodes are thesis-required. Dashed red edges are circular
dependencies. Generated {date.today().isoformat()}.</p>
<div class="legend">{legend}</div>
<div class="legend" style="margin-top:7px">{lanes_legend}</div>
</header>
{cyc_html}
<div class="wrap">{"".join(svg)}<div class="cards">{"".join(cards)}</div></div>
</body></html>'''
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out}  ({len(forks)} forks, {len(arcs)} lanes, {len(cycles)} cycle(s))")
    for k, v in counts.items():
        if v: print(f"  {STATE[k][0]:<12} {v}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Render a fork ledger as a self-contained HTML graph.")
    ap.add_argument("--ledger", help="path to the ledger JSON (default: $FORK_LEDGER or ./fork_ledger.json)")
    ap.add_argument("-o", "--out", default="fork-graph.html")
    a = ap.parse_args()
    src = ledger_path(a.ledger)
    if not src.exists():
        raise SystemExit(f"error: no ledger at {src}")
    build(json.loads(src.read_text(encoding="utf-8")), Path(a.out))
