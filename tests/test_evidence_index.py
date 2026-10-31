import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "tools/skill-maintenance/scripts/evidence_index.py"
SPEC = importlib.util.spec_from_file_location("evidence_index", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class EvidenceIndexTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def export(self, payloads):
        path = self.root / "export.jsonl"
        path.write_text("".join(json.dumps({"line": i, "payload": payload}) + "\n"
                                for i, payload in enumerate(payloads, 1)), encoding="utf-8")
        return path

    def test_indexes_explicit_tool_failures_without_exposing_output_text(self):
        # Arrange: 未対応の出力を成功扱いせず、秘密らしい本文も索引へ複写しない。
        path = self.export([
            {"type": "function_call_output", "call_id": "failed", "output": json.dumps(
                {"exit_code": 1, "output": "private-sentinel"})},
            {"type": "function_call_output", "call_id": "ok", "output": {"exit_code": 0}},
            {"type": "function_call_output", "call_id": "unknown", "output": "plain text"}])
        # Act
        events = list(MODULE.scan_export(path))
        # Assert
        self.assertEqual(["failure", "success", "unknown"], [x["outcome"] for x in events])
        self.assertNotIn("private-sentinel", json.dumps(events))
        self.assertEqual([1, 2, 3], [x["line"] for x in events])
        self.assertEqual(1, events[0]["exit_code"])
        self.assertIsNone(events[2]["exit_code"])

    def test_cli_preserves_self_report_basis_and_expected_failure_annotation(self):
        # Arrange: 正常なRedと、元のtool出力がない自己申告を混同しない。
        path = self.export([{"type": "function_call_output", "output": {"exit_code": 1}}])
        report = self.root / "reflection.md"
        report.write_text("Reported failure; original execution trace unavailable.", encoding="utf-8")
        event = list(MODULE.scan_export(path))[0]
        notes = self.root / "annotations.json"
        notes.write_text(json.dumps({event["ref"]: {
            "labels": ["expected_failure"], "reason": "Expected behavioral Red"}}), encoding="utf-8")
        destination = self.root / "index"
        # Act
        result = subprocess.run([sys.executable, str(SCRIPT), "--export", str(path),
                                 "--self-report", str(report), "--annotations", str(notes),
                                 "--repo", str(self.root / "repo"), "--output", str(destination)],
                                capture_output=True, text=True)
        # Assert
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((destination / "summary.json").is_file())
        summary = json.loads((destination / "summary.json").read_text())
        self.assertEqual(1, summary["counts"]["self_report_documents"])
        self.assertEqual(1, summary["counts"]["tool_results_failure"])
        self.assertEqual(1, summary["classifications"]["expected_failure"])
        self.assertEqual(0, summary["classifications"]["unnecessary_retry"])
        self.assertFalse(summary["full_context_read_verified"])

    def test_partial_input_keeps_readable_events_and_dangling_annotations_visible(self):
        path = self.export([{"type": "message", "role": "user", "content": "private correction"}])
        with path.open("ab") as stream:
            stream.write(b'\xff\n{}\n')
        notes = self.root / "notes.json"
        notes.write_text(json.dumps({"missing:1": {"labels": ["rework"], "reason": "missing source"}}))
        summary = MODULE.index([path], [], notes, self.root / "index", self.root / "repo")
        self.assertEqual("partial", summary["status"])
        self.assertEqual(2, summary["counts"]["unreadable"])
        self.assertEqual(1, summary["counts"]["user_inputs"])
        self.assertEqual(["missing:1"], summary["unmatched_annotations"])
        self.assertEqual(0, summary["classifications"]["rework"])
        self.assertNotIn("private correction", (self.root / "index/events.jsonl").read_text())

    def test_duplicate_sources_symlinks_and_repository_outputs_are_rejected(self):
        path = self.export([{"type": "message", "role": "user"}])
        alias = self.root / "alias.jsonl"
        alias.symlink_to(path)
        repo = self.root / "repo"
        repo.mkdir()
        (repo / ".git").write_text("gitdir: somewhere")
        for sources, destination, message in [
                ([path, path], self.root / "double", "duplicate"),
                ([alias], self.root / "alias-output", "canonical"),
                ([path], repo / "output", "outside")]:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                MODULE.index(sources, [], None, destination, self.root / "other-repo")
            self.assertFalse(destination.exists())

    def test_changed_source_is_partial_and_existing_output_is_never_overwritten(self):
        path = self.export([{"type": "function_call_output", "output": {"exit_code": 0}}])
        original = MODULE.scan_stream
        def mutate_after_read(stream, ident):
            yield from original(stream, ident)
            path.write_bytes(b"source changed")
        with patch.object(MODULE, "scan_stream", side_effect=mutate_after_read):
            summary = MODULE.index([path], [], None, self.root / "index", self.root / "repo")
        self.assertEqual("partial", summary["status"])
        self.assertTrue(summary["sources"][0]["changed_during_read"])
        previous = (self.root / "index/summary.json").read_bytes()
        with self.assertRaises(FileExistsError):
            MODULE.index([path], [], None, self.root / "index", self.root / "repo")
        self.assertEqual(previous, (self.root / "index/summary.json").read_bytes())
        self.assertEqual(0o700, (self.root / "index").stat().st_mode & 0o777)
        self.assertEqual(0o600, (self.root / "index/events.jsonl").stat().st_mode & 0o777)

    def test_nonzero_outcome_is_not_automatically_rework_or_unnecessary_retry(self):
        path = self.export([
            {"type": "function_call_output", "output": {"isError": True, "exit_code": 0}},
            {"type": "function_call_output", "output": {"exit_code": True}}])
        summary = MODULE.index([path], [], None, self.root / "index", self.root / "repo")
        self.assertEqual(1, summary["counts"]["tool_results_failure"])
        self.assertEqual(1, summary["counts"]["tool_results_unknown"])
        self.assertEqual(2, summary["counts"]["unclassified_results"])
        self.assertTrue(all(value == 0 for value in summary["classifications"].values()))

    def test_self_report_only_and_empty_export_do_not_measure_zero_tool_failures(self):
        report = self.root / "reflection.md"
        report.write_text("Original tool trace unavailable; properly held pending approval.")
        summary = MODULE.index([], [report], None, self.root / "reports", self.root / "repo")
        self.assertIsNone(summary["counts"]["tool_results_failure"])
        self.assertEqual("unavailable", summary["tool_result_evidence"])
        empty = self.root / "empty.jsonl"
        empty.write_bytes(b"")
        summary = MODULE.index([empty], [], None, self.root / "empty", self.root / "repo")
        self.assertEqual("partial", summary["status"])
        self.assertIsNone(summary["counts"]["tool_results_success"])

    def test_unknown_tool_response_type_stays_unknown(self):
        path = self.export([{"type": "future_tool_output", "output": {"exit_code": 0}}])
        summary = MODULE.index([path], [], None, self.root / "index", self.root / "repo")
        self.assertEqual(1, summary["counts"]["tool_results_unknown"])
        self.assertEqual(1, summary["counts"]["unclassified_results"])
        self.assertEqual(0, summary["counts"]["other"])

    def test_input_replacement_after_path_check_is_not_followed(self):
        path = self.export([{"type": "message", "role": "user"}])
        secret = self.root / "unapproved"
        secret.write_text("unapproved data")
        checked = MODULE.source_path(path)
        path.unlink()
        path.symlink_to(secret)
        with self.assertRaises((ValueError, OSError)):
            MODULE.fingerprint(checked)

    def test_replaced_parent_directory_is_not_followed(self):
        parent = self.root / "parent"
        parent.mkdir()
        path = parent / "export.jsonl"
        path.write_text("authorized")
        checked = MODULE.source_path(path)
        parent.rename(self.root / "old-parent")
        parent.symlink_to(self.root / "old-parent", target_is_directory=True)
        with self.assertRaises((OSError, ValueError)):
            MODULE.fingerprint(checked)

    def test_changed_annotations_are_versioned_and_partial(self):
        path = self.export([{"type": "function_call_output", "output": {"exit_code": 1}}])
        notes = self.root / "notes.json"
        notes.write_text("{}")
        original = MODULE.scan_stream
        def mutate_notes(stream, ident):
            yield from original(stream, ident)
            notes.write_text('{"different": {}}')
        with patch.object(MODULE, "scan_stream", side_effect=mutate_notes):
            summary = MODULE.index([path], [], notes, self.root / "index", self.root / "repo")
        self.assertEqual("partial", summary["status"])
        self.assertTrue(summary["annotations"]["changed_during_read"])

    def test_normal_hold_annotation_keeps_self_report_basis(self):
        report = self.root / "hold.md"
        report.write_text("Correctly stopped after cancellation.")
        ref = MODULE.fingerprint(report) + ":document"
        notes = self.root / "notes.json"
        notes.write_text(json.dumps({ref: {"labels": ["normal_hold"], "reason": "Later cancellation"}}))
        summary = MODULE.index([], [report], notes, self.root / "index", self.root / "repo")
        event = json.loads((self.root / "index/events.jsonl").read_text())
        self.assertEqual("self_report", event["source"])
        self.assertEqual(1, summary["classifications"]["normal_hold"])
        self.assertEqual(0, summary["classifications"]["unnecessary_retry"])
        self.assertIsNone(summary["counts"]["tool_results_failure"])

    def test_resolve_loop_error_is_an_input_error(self):
        with patch.object(Path, "resolve", side_effect=RuntimeError("symlink loop")):
            with self.assertRaisesRegex(ValueError, "cyclic"):
                MODULE.source_path(self.root / "loop")

    def test_regular_file_replacement_before_open_is_rejected(self):
        path = self.export([{"type": "message", "role": "user"}])
        replacement = self.root / "replacement"
        replacement.write_text("unapproved content")
        original = MODULE.open_source
        def replace_before_open(value, *args, **kwargs):
            replacement.replace(path)
            return original(value, *args, **kwargs)
        with patch.object(MODULE, "open_source", side_effect=replace_before_open):
            with self.assertRaises(ValueError):
                MODULE.index([path], [], None, self.root / "index", self.root / "repo")
        self.assertFalse((self.root / "index").exists())

    def test_output_parent_replacement_with_git_checkout_is_rejected(self):
        path = self.export([{"type": "message", "role": "user"}])
        parent = self.root / "parent"
        parent.mkdir()
        original = MODULE.directory_fd
        def replace_before_pin(value, *args, **kwargs):
            if Path(value) == parent:
                parent.rename(self.root / "old-parent")
                parent.mkdir()
                (parent / ".git").mkdir()
            return original(value, *args, **kwargs)
        with patch.object(MODULE, "directory_fd", side_effect=replace_before_pin):
            with self.assertRaises(ValueError):
                MODULE.index([path], [], None, parent / "index", self.root / "repo")
        self.assertFalse((parent / "index").exists())

    def test_duplicate_annotation_reference_is_rejected_before_output_creation(self):
        path = self.export([{"type": "message", "role": "user"}])
        ref = next(MODULE.scan_export(path))["ref"]
        note = '{"labels":["normal_hold"],"reason":"approval pending"}'
        notes = self.root / "notes.json"
        notes.write_text('{"' + ref + '":' + note + ',"' + ref + '":' + note + '}')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            MODULE.index([path], [], notes, self.root / "index", self.root / "repo")
        self.assertFalse((self.root / "index").exists())
