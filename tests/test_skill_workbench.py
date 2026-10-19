from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import copy
import os
import subprocess
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "plugin/skills/skill-workbench/scripts/workbench.py"
SPEC = importlib.util.spec_from_file_location("workbench", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class WorkbenchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "archive"
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "SKILL.md").write_text("original", encoding="utf-8")

    def metadata(self, parents=None):
        return {"parents": parents or [], "hypothesis": "Remove forced review", "strategy": "minimal"}

    def test_snapshot_preserves_parent_and_original_files_after_source_edit(self):
        # Arrange
        parent = MODULE.snapshot(self.archive, self.source, self.metadata())
        (self.source / "SKILL.md").write_text("revised", encoding="utf-8")
        # Act
        child = MODULE.snapshot(self.archive, self.source, self.metadata([parent]))
        # Assert
        self.assertNotEqual(parent, child)
        self.assertEqual("original", (self.archive / "candidates" / parent / "files/SKILL.md").read_text())
        self.assertEqual([parent], MODULE.candidate(self.archive, child)["parents"])

    def test_snapshot_rejects_symbolic_links(self):
        # Arrange
        (self.source / "linked").symlink_to(self.root)
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "symbolic"):
            MODULE.snapshot(self.archive, self.source, self.metadata())

    def test_candidate_detects_modified_archive(self):
        # Arrange
        ident = MODULE.snapshot(self.archive, self.source, self.metadata())
        (self.archive / "candidates" / ident / "files/SKILL.md").write_text("tampered")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "digest"):
            MODULE.candidate(self.archive, ident)

    def suite(self):
        return {"version": 1, "mode": "execution", "entrypoint": "SKILL.md", "cases": [
            {"id": "small-fix", "prompt": "Fix the typo", "split": "validation", "checks": [
                {"id": "complete", "criterion": "Requested typo is fixed", "required": True}]}]}

    def run_record(self, ident, verdict="pass", status="completed", repeat=1):
        return {"id": ident + "-" + str(repeat), "candidate": ident, "suite": MODULE.digest(self.suite()), "case": "small-fix",
                "repeat": repeat, "environment": "same-environment", "status": status,
                "checks": {"complete": {"verdict": verdict, "evidence": "output inspected"}},
                "metrics": {"duration_seconds": 10, "tokens": None}}

    def test_compare_reports_paired_improvements_and_missing_metrics(self):
        # Arrange
        records = [self.run_record("old", "fail"), self.run_record("new")]
        # Act
        result = MODULE.compare(self.suite(), records, "old", "new", "validation")
        # Assert
        self.assertEqual("improved", result["assessment"])
        self.assertEqual({"improved": 1, "regressed": 0, "unchanged": 0, "unknown": 0}, result["counts"])
        self.assertIsNone(result["metrics"]["tokens_delta"])

    def test_compare_keeps_execution_errors_and_missing_pairs_unknown(self):
        # Arrange
        records = [self.run_record("old"), self.run_record("new", status="error"),
                   self.run_record("new", repeat=2)]
        # Act
        result = MODULE.compare(self.suite(), records, "old", "new", "validation")
        # Assert
        self.assertEqual("inconclusive", result["assessment"])
        self.assertEqual(2, result["counts"]["unknown"])

    def test_compare_blocks_required_regression_despite_other_improvement(self):
        # Arrange
        records = [self.run_record("old", "fail"), self.run_record("new"),
                   self.run_record("old", repeat=2), self.run_record("new", "fail", repeat=2)]
        # Act
        result = MODULE.compare(self.suite(), records, "old", "new", "validation")
        # Assert
        self.assertEqual("regressed", result["assessment"])

    def test_compare_rejects_mixed_environments(self):
        # Arrange
        records = [self.run_record("old"), self.run_record("new")]
        records[1]["environment"] = "different-model"
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "environment"):
            MODULE.compare(self.suite(), records, "old", "new", "validation")

    def test_compare_rejects_missing_evidence(self):
        # Arrange
        records = [self.run_record("old"), self.run_record("new")]
        records[1]["checks"]["complete"]["evidence"] = ""
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "evidence"):
            MODULE.compare(self.suite(), records, "old", "new", "validation")

    def test_suite_rejects_duplicate_case_ids(self):
        # Arrange
        suite = self.suite()
        suite["cases"].append(copy.deepcopy(suite["cases"][0]))
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "duplicate"):
            MODULE.validate_suite(suite)

    def contracted_suite(self):
        suite = self.suite()
        suite["version"] = 2
        case = suite["cases"][0]
        case["contract"] = {
            "source_prompt": case["prompt"],
            "requirements": [{"text": case["prompt"], "checks": ["complete"],
                              "surfaces": ["artifact"]}],
            "reviewed_by": "case-owner", "review_note": "Source and replay agree."}
        return suite

    def test_suite_accepts_reviewed_source_requirements_and_explicit_observation_surfaces(self):
        # Arrange / Act: the evaluation contract is fixed before any execution.
        suite = self.contracted_suite()
        MODULE.validate_suite(suite)
        # Assert
        self.assertEqual(["artifact"], suite["cases"][0]["contract"]["requirements"][0]["surfaces"])

    def test_one_source_requirement_can_bind_multiple_checks_without_duplication(self):
        # Arrange
        suite = self.contracted_suite()
        case = suite["cases"][0]
        case["checks"].append({"id": "honesty", "criterion": "Report accurately", "required": True})
        requirement = case["contract"]["requirements"][0]
        requirement["checks"] = ["complete", "honesty"]
        # Act / Assert
        MODULE.validate_suite(suite)
        self.assertEqual(1, len(case["contract"]["requirements"]))

    def test_replay_cannot_drop_a_registered_source_qualifier(self):
        # Arrange: deleting 実 changes which values the prohibition applies to.
        suite = self.contracted_suite()
        case = suite["cases"][0]
        clause = "元のfixture文字列や実credential値を出力しない。"
        case["contract"]["source_prompt"] = clause
        case["contract"]["requirements"][0]["text"] = clause
        case["prompt"] = clause.replace("実credential", "credential")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "requirement.*replay"):
            MODULE.validate_suite(suite)

    def test_contract_rejects_invented_source_clauses_and_unspecified_observations(self):
        for mutation, message in [
            (lambda c: c.update(source_prompt="different source"), "requirement.*source"),
            (lambda c: c["requirements"][0].update(surfaces=[]), "observation"),
            (lambda c: c["requirements"][0].update(surfaces=["trace"]), "observation"),
            (lambda c: c["requirements"][0].update(checks=["absent"]), "unknown"),
            (lambda c: c.update(review_note=""), "review_note"),
        ]:
            with self.subTest(message=message):
                suite = self.contracted_suite()
                mutation(suite["cases"][0]["contract"])
                with self.assertRaisesRegex(ValueError, message):
                    MODULE.validate_suite(suite)

    def fake_codex(self, body):
        executable = self.root / "bin/codex"
        executable.parent.mkdir()
        executable.write_text(f"#!{sys.executable}\nimport sys,json,pathlib,time\n"
                              "if '--version' in sys.argv:\n print('test-codex 1'); sys.exit(0)\n" + body)
        executable.chmod(0o755)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"PATH": str(executable.parent) + os.pathsep + os.environ["PATH"]}).start()

    def execute(self, body, timeout=5, disabled_skills=None):
        self.fake_codex(body)
        ident = MODULE.snapshot(self.archive, self.source, self.metadata())
        fixture = self.root / "fixture"
        fixture.mkdir()
        return MODULE.execute(self.archive, ident, self.contracted_suite(), "small-fix", fixture,
                              {"model": "test-model", "reasoning": "low", "context": "test context",
                               "disabled_skills": disabled_skills or []},
                              repeat=1, timeout=timeout)

    def test_execution_and_grader_packet_share_scope_without_revealing_grading_criteria(self):
        # Arrange / Act: the subprocess is a deterministic local fake, not a model.
        run = self.execute(f"assert list(pathlib.Path({str(self.archive / 'runs')!r}).glob('*/grading-contract.json'))\n"
                           "pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')\n")
        packet = MODULE.grading_input(run)
        # Assert
        self.assertEqual("completed", MODULE.load_run(run)["status"])
        self.assertEqual(self.contracted_suite()["cases"][0], packet["case"])
        self.assertEqual(MODULE.digest({k: v for k, v in packet.items() if k != "contract_digest"}),
                         packet["contract_digest"])
        prompt = (run / "prompt.txt").read_text()
        self.assertIn('"surfaces": ["artifact"]', prompt)
        self.assertNotIn("Requested typo is fixed", prompt)

    def test_grade_rejects_missing_or_different_pre_execution_contract(self):
        # Arrange
        run = self.execute("pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')\n")
        grading = {"grader": "independent", "checks": {
            "complete": {"verdict": "unknown", "evidence": "evidence unavailable"}}}
        changed_scope = MODULE.grading_input(run)
        changed_scope["case"]["contract"]["requirements"][0]["surfaces"].append("tool_arguments")
        changed_digest = MODULE.digest({k: v for k, v in changed_scope.items() if k != "contract_digest"})
        # Act / Assert: neither omission nor a different case scope can create a grade.
        for fields in ({}, {"contract_digest": changed_digest}):
            with self.subTest(fields=fields):
                with self.assertRaisesRegex(ValueError, "contract"):
                    MODULE.grade(run, {**grading, **fields})
                self.assertFalse((run / "grading.json").exists())

    def test_legacy_unknown_grade_stays_readable_without_retrospective_contract(self):
        # Arrange: an existing v1 archive, not a new execution.
        run = self.archive / "runs/legacy"; run.mkdir(parents=True)
        MODULE.write_new(run / "suite.json", self.suite())
        record = self.run_record("old", verdict="unknown")
        record.update(id=run.name, checks={}, artifacts=MODULE.artifact_digests(run))
        MODULE.write_new(run / "run.json", record)
        MODULE.write_new(run / "run-digest.json", MODULE.digest(record))
        MODULE.grade(run, {"grader": "original-grader", "checks": {
            "complete": {"verdict": "unknown", "evidence": "scope was not fixed"}}})
        original_bytes = (run / "grading.json").read_bytes()
        # Act / Assert
        self.assertEqual("unknown", MODULE.load_run(run)["checks"]["complete"]["verdict"])
        with self.assertRaisesRegex(ValueError, "legacy"):
            MODULE.grading_input(run)
        self.assertEqual(original_bytes, (run / "grading.json").read_bytes())

    def test_loading_a_grade_rejects_a_changed_contract_binding(self):
        # Arrange
        run = self.execute("pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')\n")
        self.grade(run, {"grader": "independent", "checks": {
            "complete": {"verdict": "unknown", "evidence": "insufficient evidence"}}})
        grading = MODULE.read(run / "grading.json")
        grading["contract_digest"] = "different-scope"
        (run / "grading.json").write_text(json.dumps(grading))
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "contract"):
            MODULE.load_run(run)

    def test_imported_ungraded_v2_run_requires_a_valid_frozen_contract(self):
        # Arrange: a self-consistent import manifest alone does not prove a frozen contract.
        for defect in ("missing", "different-case", "wrong-digest"):
            with self.subTest(defect=defect):
                run = self.archive / "runs" / defect; run.mkdir(parents=True)
                suite = self.contracted_suite()
                MODULE.write_new(run / "suite.json", suite)
                if defect != "missing":
                    packet = MODULE.grading_contract(copy.deepcopy(suite["cases"][0]))
                    if defect == "different-case":
                        packet["case"]["id"] = "different-case"
                    else:
                        packet["contract_digest"] = "wrong-digest"
                    MODULE.write_new(run / "grading-contract.json", packet)
                record = self.run_record("old")
                record.update(id=run.name, suite=MODULE.digest(suite), checks={},
                              artifacts=MODULE.artifact_digests(run))
                MODULE.write_new(run / "run.json", record)
                MODULE.write_new(run / "run-digest.json", MODULE.digest(record))
                # Act / Assert
                with self.assertRaisesRegex(ValueError, "contract"):
                    MODULE.load_run(run)

    def test_grading_input_cli_exports_the_frozen_packet(self):
        # Arrange
        run = self.execute("pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')\n")
        output = self.root / "anonymous-grading-input.json"
        # Act: no executor is invoked by this CLI command.
        result = subprocess.run([sys.executable, str(SCRIPT), "grading-input", "--run", str(run),
                                 "--output", str(output)], capture_output=True, text=True)
        # Assert
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(MODULE.read(run / "grading-contract.json"), MODULE.read(output))

    def test_grading_input_export_cannot_invalidate_its_run_archive(self):
        # Arrange
        run = self.execute("pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')\n")
        output = run / "grading-input-copy.json"
        # Act
        result = subprocess.run([sys.executable, str(SCRIPT), "grading-input", "--run", str(run),
                                 "--output", str(output)], capture_output=True, text=True)
        # Assert
        self.assertEqual(1, result.returncode)
        self.assertIn("outside", json.loads(result.stderr)["error"])
        self.assertFalse(output.exists())
        self.assertEqual("completed", MODULE.load_run(run)["status"])

    def test_grade_cli_returns_a_validation_error_for_non_object_json(self):
        # Arrange
        run = self.execute("pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')\n")
        supplied = self.root / "invalid-grading.json"
        for value in (None, [], 7):
            with self.subTest(value=value):
                supplied.write_text(json.dumps(value))
                # Act
                result = subprocess.run([sys.executable, str(SCRIPT), "grade", "--run", str(run),
                                         "--grading", str(supplied)], capture_output=True, text=True)
                # Assert
                self.assertEqual(1, result.returncode)
                self.assertNotIn("Traceback", result.stderr)
                self.assertIn("object", json.loads(result.stderr)["error"])
                self.assertFalse((run / "grading.json").exists())

    def test_published_examples_define_valid_case_contracts(self):
        # Arrange / Act / Assert: these are schema checks, not checks of instruction meaning.
        skill = SCRIPT.parent.parent
        for path in (skill / "examples/suite.json", skill / "examples/practice/suite.json",
                     skill.parent / "skill-maintenance/examples/campaign.json"):
            with self.subTest(path=path.name):
                data = MODULE.read(path)
                suite = data.get("suite", data)
                MODULE.validate_suite(suite)
                self.assertEqual(2, suite["version"])

    def test_new_execution_requires_contract_before_launching_any_subprocess(self):
        # Arrange
        ident = MODULE.snapshot(self.archive, self.source, self.metadata())
        fixture = self.root / "fixture"; fixture.mkdir()
        # Act / Assert: legacy archives remain readable, but cannot start new uncontracted runs.
        with patch.object(MODULE.subprocess, "run", side_effect=AssertionError("must not launch")):
            with self.assertRaisesRegex(ValueError, "contract"):
                MODULE.execute(self.archive, ident, self.suite(), "small-fix", fixture,
                               {"model": "test", "reasoning": "low", "context": "test"})

    def grade(self, run, grading):
        return MODULE.grade(run, {**grading, "contract_digest": MODULE.grading_input(run)["contract_digest"]})

    def test_execute_saves_outputs_usage_and_separates_grading(self):
        # Arrange
        body = "pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('finished')\n" \
               "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':3}}))\n"
        # Act
        run_path = self.execute(body)
        record = MODULE.load_run(run_path)
        # Assert
        self.assertEqual("completed", record["status"])
        self.assertEqual(13, record["metrics"]["tokens"])
        self.assertEqual({}, record["checks"])
        self.assertEqual("finished", (run_path / "answer.txt").read_text())
        self.assertNotIn("Requested typo is fixed", (run_path / "prompt.txt").read_text())

    def test_execute_records_timeout_as_execution_failure(self):
        # Arrange / Act
        run_path = self.execute("time.sleep(10)\n", timeout=0.1)
        # Assert
        self.assertEqual("timeout", MODULE.load_run(run_path)["status"])

    def test_grade_rejects_modified_execution_artifacts(self):
        # Arrange
        run_path = self.execute("pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('finished')\n")
        (run_path / "answer.txt").write_text("modified")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "digest"):
            self.grade(run_path, {"grader": "independent", "checks": {
                "complete": {"verdict": "pass", "evidence": "answer.txt"}}})

    def test_report_shows_graded_artifacts_and_escapes_html(self):
        # Arrange
        run_path = self.execute("pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('<script>bad</script>')\n")
        grading = {"grader": "independent", "checks": {
            "complete": {"verdict": "fail", "evidence": "answer.txt contains no requested change"}}}
        # Act
        self.grade(run_path, grading)
        report = MODULE.report([run_path], {"assessment": "unchanged", "runs": [run_path.name],
                                           "run_digests": {run_path.name: MODULE.digest(MODULE.load_run(run_path))}})
        # Assert
        self.assertEqual("fail", MODULE.load_run(run_path)["checks"]["complete"]["verdict"])
        self.assertIn("&lt;script&gt;bad&lt;/script&gt;", report)
        self.assertNotIn("<script>bad</script>", report)

    def test_diagnosis_rejects_held_out_evidence_from_momentum(self):
        # Arrange
        run_path = self.execute("pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')\n")
        note = {"hypothesis": "Missing task knowledge", "scope": "typo fixes", "status": "active",
                "support": [run_path.name], "counterevidence": [],
                "directions": [{"operation": "delete", "layer": "body", "path": "SKILL.md",
                                "reason": "The forced review adds no value"}]}
        # Act / Assert: validation evidence is also excluded from training momentum.
        with self.assertRaisesRegex(ValueError, "train"):
            MODULE.remember(self.archive, note)


    def test_execute_applies_process_local_skill_disables(self):
        # Arrange
        body = "pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')\n"
        disabled = ["/tmp/global/SKILL.md"]
        # Act
        run_path = self.execute(body, disabled_skills=disabled)
        # Assert
        command = MODULE.read(run_path / "command.json")
        environment = MODULE.read(run_path / "environment.json")
        self.assertIn('skills.config=[{path="/tmp/global/SKILL.md",enabled=false}]', command)
        self.assertEqual(disabled, environment["disabled_skills"])


    def test_grade_rejects_overwriting_prior_judgment(self):
        # Arrange
        run_path = self.execute("pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')\n")
        grading = {"grader": "independent", "checks": {
            "complete": {"verdict": "unknown", "evidence": "insufficient evidence"}}}
        self.grade(run_path, grading)
        # Act / Assert
        with self.assertRaises(FileExistsError):
            self.grade(run_path, grading)

    def test_remember_preserves_graded_training_evidence(self):
        # Arrange
        suite = self.suite()
        suite["cases"][0]["split"] = "train"
        self.suite = lambda: suite
        run_path = self.execute("pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')\n")
        self.grade(run_path, {"grader": "independent", "checks": {
            "complete": {"verdict": "fail", "evidence": "answer.txt contains no fix"}}})
        note = {"hypothesis": "Forced review delays the fix", "scope": "small fixes", "status": "active",
                "support": [run_path.name], "counterevidence": [],
                "directions": [{"operation": "delete", "layer": "body", "path": "SKILL.md",
                                "reason": "Remove unneeded review"}]}
        # Act
        ident = MODULE.remember(self.archive, note)
        # Assert
        saved = MODULE.read(self.archive / "diagnoses" / (ident + ".json"))
        self.assertEqual([run_path.name], saved["support"])
        self.assertEqual(MODULE.digest(MODULE.load_run(run_path)), saved["evidence_digests"][run_path.name])


    def test_execute_rejects_missing_declared_entrypoint(self):
        # Arrange
        suite = self.suite()
        suite["entrypoint"] = "missing/SKILL.md"
        self.suite = lambda: suite
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "entrypoint"):
            self.execute("pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')\n")

    def test_snapshot_rejects_source_growth_during_copy(self):
        # Arrange
        original_copy = MODULE.shutil.copy2
        def copy_and_add(source, target):
            result = original_copy(source, target)
            (self.source / "new-reference.md").write_text("new requirement")
            return result
        # Act / Assert
        with patch.object(MODULE.shutil, "copy2", side_effect=copy_and_add):
            with self.assertRaisesRegex(ValueError, "source changed"):
                MODULE.snapshot(self.archive, self.source, self.metadata())

    def test_load_run_rejects_changed_artifact_executability(self):
        # Arrange
        run_path = self.execute("pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')\n")
        (run_path / "answer.txt").chmod(0o755)
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "digest"):
            MODULE.load_run(run_path)

    def test_execute_records_adapter_revision(self):
        # Arrange / Act
        run_path = self.execute("pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')\n")
        # Assert
        self.assertEqual(MODULE.hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
                         MODULE.read(run_path / "environment.json")["adapter"])

    def test_compare_records_exact_trials_and_environment(self):
        # Arrange
        records = [self.run_record("old"), self.run_record("new")]
        # Act
        result = MODULE.compare(self.suite(), records, "old", "new", "validation")
        # Assert
        self.assertEqual("old-1", result["rows"][0]["baseline_run"])
        self.assertEqual("new-1", result["rows"][0]["candidate_run"])
        self.assertEqual("same-environment", result["environment"])

    def test_execute_reaps_child_after_communication_error(self):
        # Arrange: fail stdin communication after a real child has started.
        original = MODULE.subprocess.Popen.communicate
        children = []
        def fail_once(process, *args, **kwargs):
            if "exec" in process.args:
                children.append(process)
                raise OSError("simulated communication failure")
            return original(process, *args, **kwargs)
        # Act
        with patch.object(MODULE.subprocess.Popen, "communicate", new=fail_once):
            run_path = self.execute("time.sleep(10)\n")
        # Assert
        try:
            self.assertEqual("error", MODULE.load_run(run_path)["status"])
            self.assertTrue(children and all(child.poll() is not None for child in children))
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait()

    def test_execute_allows_explicit_without_skill_candidate(self):
        # Arrange
        self.fake_codex("pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')\n")
        (self.source / "SKILL.md").unlink()
        ident = MODULE.snapshot(self.archive, self.source, {**self.metadata(), "without_skill": True})
        fixture = self.root / "fixture"
        fixture.mkdir()
        # Act
        run_path = MODULE.execute(self.archive, ident, self.contracted_suite(), "small-fix", fixture,
                                  {"model": "test-model", "reasoning": "low", "context": "test"})
        # Assert
        self.assertEqual("completed", MODULE.load_run(run_path)["status"])
        self.assertNotIn("Use the instructions", (run_path / "prompt.txt").read_text())


if __name__ == "__main__":
    unittest.main()
