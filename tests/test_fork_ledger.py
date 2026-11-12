# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 EngramForge, Inc.
"""Tests for fork_ledger.py. Standard library only.

    python3 -m unittest discover -s tests -v
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fork_ledger as fl  # noqa: E402
import fork_graph as fg   # noqa: E402


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ledger.json"
        self.run_cli("init")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv, expect_exit=None):
        out = io.StringIO()
        code = None
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                code = fl.main(["--ledger", str(self.path), *argv])
            except SystemExit as exc:
                code = exc.code
        if expect_exit is None:
            self.assertIn(code, (0, None), f"{argv} -> {code}\n{out.getvalue()}")
        elif expect_exit == "error":
            self.assertTrue(code not in (0, None), f"{argv} should have failed")
        else:
            self.assertEqual(code, expect_exit)
        return out.getvalue()

    def forks(self):
        return json.loads(self.path.read_text())["forks"]

    def add(self, title="t", kind="deferral", *extra):
        self.run_cli("add", "--title", title, "--kind", kind, *extra)
        return self.forks()[-1]


class TestInit(LedgerCase):
    def test_init_creates_empty_ledger_and_refuses_overwrite(self):
        data = json.loads(self.path.read_text())
        self.assertEqual(data["forks"], [])
        self.assertEqual(data["schema_version"], fl.SCHEMA_VERSION)
        self.run_cli("init", expect_exit="error")

    def test_missing_ledger_is_an_error(self):
        self.path.unlink()
        self.run_cli("wake", expect_exit="error")


class TestAdd(LedgerCase):
    def test_ids_increment(self):
        self.assertEqual(self.add()["id"], "F-001")
        self.assertEqual(self.add()["id"], "F-002")

    def test_trigger_makes_it_pending(self):
        f = self.add("a", "deferral", "--trigger", "after the migration")
        self.assertEqual(f["trigger_status"], "pending")
        self.assertEqual(f["status"], "OPEN")

    def test_no_trigger_is_unscheduled(self):
        self.assertEqual(self.add()["trigger_status"], "none")

    def test_trigger_none_is_unscheduled_not_pending(self):
        for text in ("none", "None", "none — nobody owns it", "none: tbd"):
            f = self.add("a", "open-question", "--trigger", text)
            self.assertEqual(f["trigger_status"], "none", text)
        self.assertEqual(self.run_cli("check").strip(), "ledger clean.")

    def test_bad_kind_and_bad_thesis_rejected(self):
        self.run_cli("add", "--title", "x", "--kind", "wish", expect_exit="error")
        self.run_cli("add", "--title", "x", "--kind", "deferral", "--thesis", "maybe", expect_exit="error")
        self.assertEqual(self.forks(), [])

    def test_depends_on_must_exist(self):
        self.add()
        f = self.add("b", "deferral", "--depends-on", "f-001")
        self.assertEqual(f["depends_on"], ["F-001"])
        self.run_cli("add", "--title", "c", "--kind", "deferral", "--depends-on", "F-099", expect_exit="error")


class TestLifecycle(LedgerCase):
    def test_close_requires_reason(self):
        self.add()
        self.run_cli("close", "F-001", expect_exit="error")
        self.assertEqual(self.forks()[0]["status"], "OPEN")
        self.run_cli("close", "F-001", "--by", "covered elsewhere")
        f = self.forks()[0]
        self.assertEqual((f["status"], f["closed_by"]), ("CLOSED", "covered elsewhere"))

    def test_supersede_cites_successor(self):
        self.add()
        self.run_cli("close", "F-001", "--by", "F-002 replaces it", "--superseded")
        f = self.forks()[0]
        self.assertEqual((f["status"], f["superseded_by"]), ("SUPERSEDED", "F-002 replaces it"))

    def test_fire_orphan_park_record_history(self):
        self.add("a", "deferral", "--trigger", "when X")
        self.run_cli("fire", "F-001", "--note", "X happened")
        self.run_cli("orphan", "F-001", "--note", "X was cancelled")
        self.run_cli("park", "F-001", "--trigger", "when Y")
        f = self.forks()[0]
        self.assertEqual((f["trigger"], f["trigger_status"]), ("when Y", "pending"))
        self.assertEqual(len(f["history"]), 3)

    def test_park_refuses_none(self):
        self.add()
        self.run_cli("park", "F-001", "--trigger", "none", expect_exit="error")

    def test_nothing_is_deleted(self):
        self.add(); self.add()
        self.run_cli("close", "F-001", "--by", "done")
        self.assertEqual(len(self.forks()), 2)

    def test_cannot_start_a_resolved_fork(self):
        self.add()
        self.run_cli("close", "F-001", "--by", "done")
        self.run_cli("start", "F-001", expect_exit="error")


class TestWake(LedgerCase):
    def test_each_category_surfaces(self):
        self.add("parked", "deferral", "--trigger", "when A")          # F-001 parked
        self.add("fired", "deferral", "--trigger", "when B")           # F-002
        self.add("orphaned", "deferral", "--trigger", "when C")        # F-003
        self.add("unscheduled", "open-question")                       # F-004
        self.add("inflight", "deferral", "--trigger", "when D")        # F-005
        self.add("closed", "deferral", "--trigger", "when E")          # F-006
        self.run_cli("fire", "F-002"); self.run_cli("orphan", "F-003")
        self.run_cli("start", "F-005"); self.run_cli("close", "F-006", "--by", "done")
        out = self.run_cli("wake")
        for label, fid in (("TRIGGER FIRED", "F-002"), ("ORPHANED TRIGGER", "F-003"),
                           ("UNSCHEDULED", "F-004"), ("ACTIVE", "F-005")):
            self.assertIn(label, out)
            self.assertIn(fid, out)
        self.assertNotIn("F-001", out)   # legitimately parked
        self.assertNotIn("F-006", out)   # resolved

    def test_fired_outranks_active(self):
        self.add("a", "deferral", "--trigger", "when A")
        self.run_cli("start", "F-001"); self.run_cli("fire", "F-001")
        self.assertEqual(fl.derived_state(self.forks()[0]), "fired")

    def test_quiet_ledger_says_so(self):
        self.add("parked", "deferral", "--trigger", "when A")
        self.assertIn("Nothing awake", self.run_cli("wake"))


class TestCheck(LedgerCase):
    def write(self, forks):
        self.path.write_text(json.dumps({"schema_version": "0.1", "updated": "", "forks": forks}))

    def base(self, **over):
        f = {"id": "F-001", "title": "t", "kind": "deferral", "opened": "2026-01-01", "status": "OPEN",
             "trigger": "when A", "trigger_status": "pending", "thesis_dep": "unrelated"}
        f.update(over)
        return f

    def test_flags_each_problem(self):
        self.write([self.base(),
                    self.base(id="F-002", status="CLOSED"),
                    self.base(id="F-003", trigger="none"),
                    self.base(id="F-004", depends_on=["F-777"]),
                    self.base(id="F-005", kind="wish")])
        out = self.run_cli("check", expect_exit=1)
        for needle in ("F-002: closed with no reason", "F-003: pending trigger but no condition",
                       "F-004: depends_on F-777 does not exist", "F-005: bad kind wish"):
            self.assertIn(needle, out)
        self.assertNotIn("F-001", out)

    def test_fix_reclassifies_and_records_history(self):
        self.write([self.base(trigger="none — tbd")])
        self.run_cli("check", expect_exit=1)
        out = self.run_cli("check", "--fix")
        self.assertIn("ledger clean.", out)
        f = self.forks()[0]
        self.assertEqual(f["trigger_status"], "none")
        self.assertEqual(len(f["history"]), 1)

    def test_older_ledgers_without_arc_or_depends_on_load(self):
        self.write([self.base()])
        self.assertIn("ledger clean.", self.run_cli("check"))
        self.run_cli("wake"); self.run_cli("report"); self.run_cli("show", "F-001")


class TestPriorworkAndReport(LedgerCase):
    def test_priorwork_searches_ledger_and_documents(self):
        self.add("Cache invalidation on session writes", "deferral")
        docs = Path(self.tmp.name) / "docs"; docs.mkdir()
        (docs / "a.md").write_text("Notes on cache invalidation and sessions.")
        (docs / "b.md").write_text("Unrelated.")
        out = self.run_cli("priorwork", "cache", "invalidation", "--in", str(docs))
        self.assertIn("F-001", out)
        self.assertIn("a.md", out)
        self.assertNotIn("b.md", out)

    def test_priorwork_no_hits_says_to_record_it(self):
        self.assertIn("No hits", self.run_cli("priorwork", "zebra"))

    def test_report_groups_by_state(self):
        self.add("u", "open-question")
        self.add("p", "deferral", "--trigger", "when A")
        out_file = Path(self.tmp.name) / "r.md"
        self.run_cli("report", "-o", str(out_file))
        text = out_file.read_text()
        self.assertIn("## Unscheduled", text)
        self.assertIn("## Parked", text)


class TestGraph(unittest.TestCase):
    def test_cycle_detection(self):
        forks = [{"id": "F-001", "depends_on": ["F-002"]}, {"id": "F-002", "depends_on": ["F-001"]},
                 {"id": "F-003", "depends_on": ["F-001"]}]
        cycles = fg.find_cycles(forks)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(set(cycles[0]), {"F-001", "F-002"})

    def test_example_ledger_renders(self):
        example = Path(__file__).resolve().parent.parent / "examples" / "fork_ledger.example.json"
        data = json.loads(example.read_text())
        self.assertEqual(fl.problems_in(data), [])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "g.html"
            with contextlib.redirect_stdout(io.StringIO()):
                fg.build(data, out)
            page = out.read_text()
        for f in data["forks"]:
            self.assertIn(f'id="c-{f["id"]}"', page)
        self.assertIn("ORPHANED", page)


if __name__ == "__main__":
    unittest.main()
