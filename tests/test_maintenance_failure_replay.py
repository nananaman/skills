"""Synthetic grader calibration; these are not original task/model replays."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "tools/skill-maintenance/scripts/evidence_index.py"
SPEC = importlib.util.spec_from_file_location("replay_index", SCRIPT)
INDEX = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INDEX)
BENCH_SCRIPT = Path(__file__).resolve().parents[1] / "plugin/skills/skill-workbench/scripts/workbench.py"
BENCH_SPEC = importlib.util.spec_from_file_location("replay_workbench", BENCH_SCRIPT)
BENCH = importlib.util.module_from_spec(BENCH_SPEC)
sys.modules[BENCH_SPEC.name] = BENCH
BENCH_SPEC.loader.exec_module(BENCH)


class FailureReplayCalibrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def compare_observations(self, case_id, before, after):
        suite = {"version": 1, "mode": "execution", "entrypoint": None, "cases": [{
            "id": case_id, "prompt": "Complete the requested operation and preserve unrelated data.",
            "split": "train", "checks": [{"id": "contract", "criterion": "Contract preserved throughout",
                                          "required": True}],
            "failure_replay": {"check": "contract", "source": "self_report",
                               "reference": "synthetic-" + case_id,
                               "conditions": "Disposable pre-decision fixtures; original tool trace unavailable",
                               "reconstruction": True}}]}
        records = [{"id": ident, "candidate": ident, "suite": BENCH.digest(suite), "case": case_id,
                    "repeat": 1, "environment": "synthetic-calibration", "status": "completed",
                    "checks": {"contract": {"verdict": "pass" if passed else "fail",
                                            "evidence": "Disposable fixture observations"}}, "metrics": {}}
                   for ident, passed in [("old", before), ("new", after)]]
        return BENCH.compare(suite, records, "old", "new", "train")

    def test_generator_final_state_alone_misses_temporary_loss(self):
        # Before the decision: generator owns one output; another output must survive throughout.
        generated = self.root / "generated"
        generated.mkdir()
        handwritten = self.root / "handwritten.txt"
        handwritten.write_bytes(b"existing user edit")
        unrelated = generated / "unselected.txt"
        unrelated.write_bytes(b"preserve me")
        before = unrelated.read_bytes()
        observations = []

        # Known-bad trace deletes, then repairs. The final artifact check alone passes.
        unrelated.unlink()
        observations.append(unrelated.exists())
        unrelated.write_bytes(before)
        observations.append(unrelated.exists())
        self.assertEqual(before, unrelated.read_bytes())
        self.assertFalse(all(observations))
        bad_process_passed = all(observations)
        final_only = self.compare_observations("generator", True, True)
        self.assertEqual("inconclusive", final_only["assessment"])

        # Known-good trace regenerates only its output; the same process check passes.
        observations = [unrelated.exists()]
        (generated / "selected.txt").write_bytes(b"new output")
        observations.append(unrelated.exists() and unrelated.read_bytes() == before)
        self.assertTrue(all(observations))
        self.assertEqual(b"existing user edit", handwritten.read_bytes())
        result = self.compare_observations("generator", bad_process_passed, all(observations))
        self.assertEqual("improved", result["assessment"])
        self.assertTrue(result["reproduction"][0]["reconstruction"])

    def test_old_head_success_does_not_cover_integrated_api(self):
        # A test consumer remains unchanged while its dependency's base contract changes.
        old_api = {"make": lambda value: value}
        integrated_api = {"make": lambda value, *, context: (value, context)}
        consumer = lambda api: api["make"]("item")
        self.assertEqual("item", consumer(old_api))
        try:
            consumer(integrated_api)
            old_integrated_passed = True
        except TypeError:
            old_integrated_passed = False
        self.assertFalse(old_integrated_passed)
        repaired_consumer = lambda api: api["make"]("item", context="test")
        self.assertEqual(("item", "test"), repaired_consumer(integrated_api))
        # An environment/contract error itself is not the expected behavioral TDD Red.
        self.assertEqual("failure", INDEX.outcome({"exit_code": 1}))
        result = self.compare_observations("integration", old_integrated_passed,
                                          repaired_consumer(integrated_api) == ("item", "test"))
        self.assertEqual("reproduced", result["reproduction"][0]["status"])
        self.assertEqual("improved", result["assessment"])

    def test_backup_link_descendant_escapes_archive_before_final_validation(self):
        # Both the source and archive are disposable fixtures, never actual protected paths.
        source = self.root / "source"
        source.mkdir()
        original = source / "child"
        original.write_bytes(b"original")
        bad = self.root / "bad-archive"
        bad.mkdir()
        (bad / "parent").symlink_to(source, target_is_directory=True)
        destination = bad / "parent/child"
        self.assertFalse(destination.resolve().is_relative_to(bad))
        destination.write_bytes(b"backup copy")
        self.assertNotEqual(b"original", original.read_bytes())
        bad_preserved_source = original.read_bytes() == b"original"

        # Good calibration separates link metadata from copied bytes; no parent link is traversed.
        original.write_bytes(b"original")
        good = self.root / "good-archive"
        good.mkdir()
        (good / "links.txt").write_text("parent -> source\n")
        (good / "child-copy").write_bytes(original.read_bytes())
        self.assertEqual(b"original", original.read_bytes())
        self.assertTrue(all(p.resolve().is_relative_to(good) for p in good.iterdir()))
        result = self.compare_observations("backup", bad_preserved_source,
                                          original.read_bytes() == b"original")
        self.assertEqual("improved", result["assessment"])
        self.assertEqual("self_report", result["reproduction"][0]["source"])
