#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 EngramForge, Inc.
"""Fork Ledger — a record of paths not taken.

Every piece of work forks. One branch gets walked; the others get parked,
usually without anyone recording that they were parked. This ledger is that
record: open questions, deferrals with wake conditions, unchosen branches,
and things that were designed but never built.

Design constraints (deliberate):
  - Plain JSON. No database, no service, no dependencies beyond the stdlib.
  - Append and amend, never silently delete. Closing requires a reason.
  - The tool does NOT evaluate triggers. People (or an agent) do; the tool
    tracks what they decided.
  - Orphaned triggers (conditions that can never fire) and unscheduled items
    (no condition at all) are first-class, because that is how work dies
    quietly.

Usage:
    fork_ledger.py init                              # create an empty ledger
    fork_ledger.py add --title "..." --kind deferral --trigger "..." [...]
    fork_ledger.py wake                              # the actionable set; read this first
    fork_ledger.py list [--status OPEN] [--trigger FIRED] [--thesis REQUIRED]
    fork_ledger.py show F-001
    fork_ledger.py fire F-002 --note "the data landed"
    fork_ledger.py orphan F-001 --note "that experiment was cancelled"
    fork_ledger.py park F-005 --trigger "after the migration"
    fork_ledger.py close F-006 --by "covered by the v2 redesign"
    fork_ledger.py report [-o fork-ledger-report.md]
    fork_ledger.py check                             # integrity; suitable for pre-commit
    fork_ledger.py priorwork cache invalidation --in docs/ notes.md

The ledger file is chosen by --ledger, then the FORK_LEDGER environment
variable, then ./fork_ledger.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

__version__ = "0.2.0"
SCHEMA_VERSION = "0.2"

KINDS = {"deferral", "unchosen-branch", "designed-not-built", "open-question", "doctrine-todo"}
STATUSES = {"OPEN", "ACTIVE", "CLOSED", "SUPERSEDED"}
TRIGGERS = {"pending", "FIRED", "orphaned", "none"}
THESIS = {"REQUIRED", "helpful", "unrelated"}

FIELDS = ["id", "title", "kind", "arc", "opened", "source", "summary", "parked_because",
          "trigger", "trigger_status", "status", "thesis_dep", "cost", "owner",
          "depends_on", "refs"]

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".adoc", ".org"}


def ledger_path(arg: str | None) -> Path:
    return Path(arg or os.environ.get("FORK_LEDGER") or "fork_ledger.json")


def load(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"error: no ledger at {path}. Run `fork_ledger.py init` or pass --ledger.")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def save(data: dict, path: Path) -> None:
    data["updated"] = date.today().isoformat()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    tmp.replace(path)


def find(data: dict, fork_id: str) -> dict:
    for f in data["forks"]:
        if f["id"].upper() == fork_id.upper():
            return f
    sys.exit(f"error: no fork {fork_id}")


def next_id(data: dict) -> str:
    nums = [int(f["id"].split("-")[1]) for f in data["forks"] if f["id"].startswith("F-")]
    return f"F-{max(nums, default=0) + 1:03d}"


def is_unscheduled_text(trigger: str | None) -> bool:
    """A missing trigger, or one spelled 'none' / 'none — <why>', is no trigger at all."""
    if trigger is None:
        return True
    t = trigger.strip().lower()
    return t == "" or t == "none" or t.startswith(("none ", "none-", "none—", "none–", "none:"))


def derived_state(f: dict) -> str:
    """One word for where a fork stands; the most urgent reading wins."""
    if f["status"] in ("CLOSED", "SUPERSEDED"):
        return "resolved"
    ts = f.get("trigger_status", "none")
    if ts == "FIRED":
        return "fired"
    if ts == "orphaned":
        return "orphaned"
    if f["status"] == "ACTIVE":
        return "active"
    if ts == "none":
        return "unscheduled"
    return "parked"


def _line(f: dict) -> str:
    mark = {"FIRED": "!", "orphaned": "x", "pending": " ", "none": " "}.get(f.get("trigger_status", ""), " ")
    dep = {"REQUIRED": "***", "helpful": " * ", "unrelated": "   "}.get(f.get("thesis_dep", ""), "   ")
    return f"{mark} {f['id']}  {dep}  [{f['status']:<10}] {f['title'][:74]}"


def cmd_init(args, path: Path):
    if path.exists():
        sys.exit(f"error: {path} already exists; refusing to overwrite.")
    save({"schema_version": SCHEMA_VERSION, "updated": "", "forks": []}, path)
    print(f"created empty ledger at {path}")


def cmd_list(args, data, path):
    forks = data["forks"]
    if args.status:
        forks = [f for f in forks if f["status"] == args.status.upper()]
    if args.trigger:
        forks = [f for f in forks if f.get("trigger_status", "") == args.trigger]
    if args.thesis:
        forks = [f for f in forks if f.get("thesis_dep", "") == args.thesis]
    if args.kind:
        forks = [f for f in forks if f.get("kind", "") == args.kind]
    if args.owner:
        forks = [f for f in forks if f.get("owner", "") == args.owner]
    if args.arc:
        forks = [f for f in forks if f.get("arc", "") == args.arc]
    for f in forks:
        print(_line(f))
    print(f"\n{len(forks)} fork(s).  legend: ! trigger fired · x orphaned trigger · *** thesis-required")


def cmd_wake(args, data, path):
    """The actionable set: triggers that fired, triggers that can never fire,
    work in flight, and open items with no wake condition at all."""
    groups = {"active": [], "fired": [], "orphaned": [], "unscheduled": []}
    for f in data["forks"]:
        s = derived_state(f)
        if s in groups:
            groups[s].append(f)
    if groups["active"]:
        print("ACTIVE — in flight now:")
        for f in groups["active"]:
            print(_line(f))
        print()
    if groups["fired"]:
        print("TRIGGER FIRED — the condition these were waiting on has happened:")
        for f in groups["fired"]:
            print(_line(f))
            print(f"      trigger: {f.get('trigger', '')}")
        print()
    if groups["orphaned"]:
        print("ORPHANED TRIGGER — waiting on something that can never happen:")
        for f in groups["orphaned"]:
            print(_line(f))
            print(f"      dead trigger: {f.get('trigger', '')}")
        print()
    if groups["unscheduled"]:
        print("UNSCHEDULED — no wake condition; these surface only if someone looks:")
        for f in groups["unscheduled"]:
            print(_line(f))
        print()
    if not any(groups.values()):
        print("Nothing awake. All open forks are parked behind a stated condition.")


def cmd_show(args, data, path):
    f = find(data, args.id)
    for k in FIELDS:
        if k in f and f[k] not in ("", [], None):
            v = ", ".join(f[k]) if isinstance(f[k], list) else f[k]
            print(f"{k:>16}: {v}")
    for k in ("closed_by", "superseded_by", "history"):
        if f.get(k):
            v = f[k] if isinstance(f[k], str) else json.dumps(f[k], indent=2, ensure_ascii=False)
            print(f"{k:>16}: {v}")


def _hist(f: dict, note: str) -> None:
    f.setdefault("history", []).append({"date": date.today().isoformat(), "note": note})


def _check_deps(data: dict, deps: list[str], own_id: str | None = None) -> list[str]:
    ids = {f["id"].upper() for f in data["forks"]}
    out = []
    for d in deps:
        d = d.upper()
        if d not in ids:
            sys.exit(f"error: --depends-on {d} is not a fork in this ledger")
        if own_id and d == own_id.upper():
            sys.exit("error: a fork cannot depend on itself")
        out.append(d)
    return out


def cmd_add(args, data, path):
    if args.kind not in KINDS:
        sys.exit(f"error: kind must be one of {sorted(KINDS)}")
    if args.thesis and args.thesis not in THESIS:
        sys.exit(f"error: thesis must be one of {sorted(THESIS)}")
    unscheduled = is_unscheduled_text(args.trigger)
    f = {
        "id": next_id(data), "title": args.title, "kind": args.kind,
        "arc": args.arc or "misc",
        "opened": date.today().isoformat(), "source": args.source or "",
        "summary": args.summary or "", "parked_because": args.parked_because or "",
        "trigger": (args.trigger.strip() if args.trigger else "none"),
        "trigger_status": "none" if unscheduled else "pending",
        "status": "OPEN", "thesis_dep": args.thesis or "unrelated",
        "cost": args.cost or "unknown", "owner": args.owner or "operator",
        "depends_on": _check_deps(data, args.depends_on or []),
        "refs": args.refs or [],
    }
    data["forks"].append(f)
    save(data, path)
    where = "UNSCHEDULED (no wake condition)" if unscheduled else f"parked; wakes on: {f['trigger']}"
    print(f"added {f['id']}: {f['title']}  [{where}]")


def cmd_fire(args, data, path):
    f = find(data, args.id)
    f["trigger_status"] = "FIRED"
    _hist(f, f"trigger fired: {args.note or ''}")
    save(data, path)
    print(f"{f['id']} trigger FIRED — now in `wake`.")


def cmd_orphan(args, data, path):
    f = find(data, args.id)
    f["trigger_status"] = "orphaned"
    _hist(f, f"trigger orphaned: {args.note or ''}")
    save(data, path)
    print(f"{f['id']} trigger orphaned — surfaced in `wake` for re-triggering or closure.")


def cmd_park(args, data, path):
    f = find(data, args.id)
    if is_unscheduled_text(args.trigger):
        sys.exit("error: park needs a real condition. To record 'no condition', leave the fork "
                 "unscheduled; it will keep showing in `wake` until it gets one.")
    if args.depends_on is not None:
        f["depends_on"] = _check_deps(data, args.depends_on, own_id=f["id"])
    f["trigger"] = args.trigger.strip()
    f["trigger_status"] = "pending"
    f["status"] = "OPEN"
    _hist(f, f"parked with trigger: {f['trigger']}")
    save(data, path)
    print(f"{f['id']} parked. wakes on: {f['trigger']}")


def cmd_start(args, data, path):
    f = find(data, args.id)
    if f["status"] in ("CLOSED", "SUPERSEDED"):
        sys.exit(f"error: {f['id']} is {f['status'].lower()}; open a new fork that cites it instead.")
    f["status"] = "ACTIVE"
    _hist(f, f"started: {args.note or ''}")
    save(data, path)
    print(f"{f['id']} ACTIVE — in flight.")


def cmd_close(args, data, path):
    if not args.by:
        sys.exit("error: --by is required. Closing without a reason is how work disappears.")
    f = find(data, args.id)
    f["status"] = "SUPERSEDED" if args.superseded else "CLOSED"
    key = "superseded_by" if args.superseded else "closed_by"
    f[key] = args.by
    _hist(f, f"{f['status'].lower()}: {args.by}")
    save(data, path)
    print(f"{f['id']} {f['status'].lower()} — {args.by}")


def problems_in(data: dict) -> list[str]:
    problems = []
    ids = [f["id"] for f in data["forks"]]
    if len(ids) != len(set(ids)):
        problems.append("duplicate ids")
    known = {i.upper() for i in ids}
    for f in data["forks"]:
        if f.get("kind") not in KINDS:
            problems.append(f"{f['id']}: bad kind {f.get('kind')}")
        if f.get("status") not in STATUSES:
            problems.append(f"{f['id']}: bad status {f.get('status')}")
        if f.get("trigger_status") not in TRIGGERS:
            problems.append(f"{f['id']}: bad trigger_status {f.get('trigger_status')}")
        if f.get("thesis_dep") not in THESIS:
            problems.append(f"{f['id']}: bad thesis_dep {f.get('thesis_dep')}")
        if f["status"] in ("CLOSED", "SUPERSEDED") and not (f.get("closed_by") or f.get("superseded_by")):
            problems.append(f"{f['id']}: closed with no reason")
        if f["status"] in ("OPEN", "ACTIVE") and f.get("trigger_status") == "pending" \
                and is_unscheduled_text(f.get("trigger")):
            problems.append(f"{f['id']}: pending trigger but no condition — will never wake")
        for d in f.get("depends_on", []) or []:
            if d.upper() not in known:
                problems.append(f"{f['id']}: depends_on {d} does not exist")
    return problems


def cmd_check(args, data, path):
    problems = problems_in(data)
    if args.fix:
        fixed = 0
        for f in data["forks"]:
            if f["status"] in ("OPEN", "ACTIVE") and f.get("trigger_status") == "pending" \
                    and is_unscheduled_text(f.get("trigger")):
                f["trigger_status"] = "none"
                _hist(f, "check --fix: trigger text is 'none'; reclassified pending -> unscheduled")
                fixed += 1
        if fixed:
            save(data, path)
            print(f"fixed {fixed} fork(s): pending-with-no-condition -> unscheduled")
        problems = problems_in(data)
    print("\n".join(problems) if problems else "ledger clean.")
    return 1 if problems else 0


def _text_files(paths: list[str]) -> list[Path]:
    out = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            out.extend(sorted(q for q in p.rglob("*") if q.is_file() and q.suffix.lower() in TEXT_SUFFIXES))
        elif p.is_file():
            out.append(p)
        else:
            print(f"  (skipped: {raw} not found)")
    return out


def cmd_priorwork(args, data, path):
    """Search the ledger, and any documents you point at, before starting
    something new. Running this costs nothing, so skipping it is a choice,
    not an oversight. It finds candidates; it does not judge them."""
    terms = [t.lower() for raw in args.keywords for t in raw.split()]
    if not terms:
        sys.exit("error: at least one keyword required")
    cap = args.max
    print(f"priorwork sweep: {terms}\n")

    fork_hits = []
    for f in data["forks"]:
        haystack = " ".join([
            f.get("title", ""), f.get("summary", ""), f.get("parked_because", ""),
            f.get("trigger", ""), f.get("kind", ""), " ".join(f.get("refs", []) or []),
        ]).lower()
        n = sum(1 for t in terms if t in haystack)
        if n:
            fork_hits.append((n, f))
    fork_hits.sort(key=lambda x: -x[0])
    print(f"FORK LEDGER — {len(fork_hits)} hit(s)" + (f", showing top {cap}" if len(fork_hits) > cap else ""))
    for n, f in fork_hits[:cap]:
        print(f"  [{n}] {f['id']}  [{f['status']:<10}]  {f['title'][:80]}")
    print()

    doc_hits = []
    files = _text_files(args.paths or [])
    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        # Presence per distinct term, not raw occurrence count: a document that
        # repeats one generic term many times must not outrank one that
        # actually discusses every searched concept.
        n = sum(1 for t in terms if t in text)
        if n:
            doc_hits.append((n, fp))
    doc_hits.sort(key=lambda x: (-x[0], str(x[1])))
    if args.paths:
        print(f"DOCUMENTS — {len(doc_hits)} of {len(files)} file(s) with a hit"
              + (f", showing top {cap}" if len(doc_hits) > cap else ""))
        for n, fp in doc_hits[:cap]:
            print(f"  [{n}/{len(terms)}] {fp}")
        print()

    total = len(fork_hits) + len(doc_hits)
    if total == 0:
        print("No hits. Record that explicitly (\"no prior work found\", with these search terms) "
              "instead of proceeding as if the sweep was never run.")
    else:
        print(f"{total} hit(s). Read each one before deciding it is prior work or noise.")


def cmd_report(args, data, path):
    forks = data["forks"]

    def sect(title, items, show_trigger=True):
        if not items:
            return ""
        out = [f"\n## {title}\n"]
        for f in items:
            dep = {"REQUIRED": " **[thesis-required]**", "helpful": " *(helpful)*"}.get(f.get("thesis_dep"), "")
            out.append(f"### {f['id']} — {f['title']}{dep}\n")
            out.append(f"{f.get('summary', '')}\n")
            if f.get("parked_because"):
                out.append(f"- **Parked because:** {f['parked_because']}")
            if show_trigger and not is_unscheduled_text(f.get("trigger")):
                out.append(f"- **Trigger:** {f['trigger']} — `{f.get('trigger_status')}`")
            if f.get("depends_on"):
                out.append(f"- **Depends on:** {', '.join(f['depends_on'])}")
            if f.get("closed_by") or f.get("superseded_by"):
                out.append(f"- **Resolved by:** {f.get('closed_by') or f.get('superseded_by')}")
            out.append(f"- Opened {f.get('opened', '')} · owner {f.get('owner', '')} · "
                       f"cost {f.get('cost', '')} · source `{f.get('source', '')}`\n")
        return "\n".join(out)

    by = {}
    for f in forks:
        by.setdefault(derived_state(f), []).append(f)
    parked = by.get("parked", [])
    req = [f for f in parked if f.get("thesis_dep") == "REQUIRED"]
    rest = [f for f in parked if f not in req]
    done = by.get("resolved", [])
    n_open = len(forks) - len(done)

    md = ["# Fork Ledger — Report\n",
          f"*Generated {date.today().isoformat()} · {n_open} open · {len(done)} resolved*\n",
          "\nThe record of paths not taken: deferrals with wake conditions, unchosen branches, ",
          "designed-but-unbuilt components, and open questions.\n",
          f"\n**Attention now:** {len(by.get('active', []))} active · {len(by.get('fired', []))} triggers fired · "
          f"{len(by.get('orphaned', []))} orphaned triggers · {len(by.get('unscheduled', []))} unscheduled\n"]
    md.append(sect("Active — in flight", by.get("active", [])))
    md.append(sect("Triggers fired — the wait is over", by.get("fired", [])))
    md.append(sect("Orphaned triggers — waiting on something that can never happen", by.get("orphaned", [])))
    md.append(sect("Unscheduled — no wake condition", by.get("unscheduled", []), show_trigger=False))
    md.append(sect("Thesis-required, parked", req))
    md.append(sect("Parked", rest))
    md.append(sect("Resolved", done, show_trigger=False))
    text = "".join(md)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fork Ledger — a record of paths not taken.")
    p.add_argument("--version", action="version", version=f"fork_ledger {__version__}")
    p.add_argument("--ledger", help="path to the ledger JSON (default: $FORK_LEDGER or ./fork_ledger.json)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create an empty ledger").set_defaults(fn=cmd_init)

    s = sub.add_parser("list")
    for flag in ("--status", "--trigger", "--thesis", "--kind", "--owner", "--arc"):
        s.add_argument(flag)
    s.set_defaults(fn=cmd_list)

    sub.add_parser("wake", help="the actionable set; read this first").set_defaults(fn=cmd_wake)

    s = sub.add_parser("show"); s.add_argument("id"); s.set_defaults(fn=cmd_show)

    s = sub.add_parser("add")
    s.add_argument("--title", required=True); s.add_argument("--kind", required=True)
    s.add_argument("--summary"); s.add_argument("--source")
    s.add_argument("--parked-because", dest="parked_because")
    s.add_argument("--trigger", help="the wake condition in plain language; omit or pass 'none' for unscheduled")
    s.add_argument("--thesis", help="REQUIRED | helpful | unrelated")
    s.add_argument("--cost"); s.add_argument("--owner")
    s.add_argument("--arc", help="the line of work this belongs to (a lane in the graph)")
    s.add_argument("--depends-on", dest="depends_on", nargs="*", help="ids of forks this one needs first")
    s.add_argument("--refs", nargs="*")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("fire"); s.add_argument("id"); s.add_argument("--note"); s.set_defaults(fn=cmd_fire)
    s = sub.add_parser("orphan"); s.add_argument("id"); s.add_argument("--note"); s.set_defaults(fn=cmd_orphan)
    s = sub.add_parser("park"); s.add_argument("id"); s.add_argument("--trigger", required=True)
    s.add_argument("--depends-on", dest="depends_on", nargs="*")
    s.set_defaults(fn=cmd_park)
    s = sub.add_parser("start", help="mark a fork ACTIVE"); s.add_argument("id"); s.add_argument("--note")
    s.set_defaults(fn=cmd_start)
    s = sub.add_parser("close"); s.add_argument("id"); s.add_argument("--by")
    s.add_argument("--superseded", action="store_true")
    s.set_defaults(fn=cmd_close)
    s = sub.add_parser("check", help="integrity check; exits 1 on problems")
    s.add_argument("--fix", action="store_true", help="reclassify pending-with-no-condition forks as unscheduled")
    s.set_defaults(fn=cmd_check)
    s = sub.add_parser("report"); s.add_argument("-o", "--out"); s.set_defaults(fn=cmd_report)

    s = sub.add_parser("priorwork", help="search the ledger and your documents before starting something new")
    s.add_argument("keywords", nargs="+", help="search terms, e.g. cache invalidation")
    s.add_argument("--in", dest="paths", nargs="*", help="files or directories of text/markdown to search too")
    s.add_argument("--max", type=int, default=15, help="max hits shown per source (default 15)")
    s.set_defaults(fn=cmd_priorwork)

    args = p.parse_args(argv)
    path = ledger_path(args.ledger)
    if args.cmd == "init":
        cmd_init(args, path)
        return 0
    data = load(path)
    return args.fn(args, data, path) or 0


if __name__ == "__main__":
    sys.exit(main())
