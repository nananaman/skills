#!/usr/bin/env python3
"""Local experiment storage and Codex execution for skill-workbench (Python 3.11+)."""

import argparse
import hashlib
import importlib.util
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid


_RESTRICTED_SPEC = importlib.util.spec_from_file_location('workbench_restricted_runner',
    Path(__file__).with_name('restricted_runner.py'))
restricted_runner = importlib.util.module_from_spec(_RESTRICTED_SPEC)
_RESTRICTED_SPEC.loader.exec_module(restricted_runner)


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def identifier(value: str) -> str:
    require(isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_-]+", value), "invalid identifier")
    return value


def file_digests(root: Path) -> dict:
    result = {}
    for path in sorted(root.rglob("*")):
        if any(part in {".git", "__pycache__"} for part in path.relative_to(root).parts):
            continue
        require(not path.is_symlink(), "symbolic links are not supported")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "executable": bool(path.stat().st_mode & 0o111),
            }
        else:
            require(path.is_dir(), "only regular files and directories are supported")
    return result


def candidate(archive: Path, ident: str) -> dict:
    folder = archive / "candidates" / identifier(ident)
    record = read(folder / "candidate.json")
    require(digest(record) == ident, "candidate metadata digest mismatch")
    require(file_digests(folder / "files") == record["files"], "candidate file digest mismatch")
    return record


def snapshot(archive: Path, source: Path, metadata: dict) -> str:
    require(source.is_dir() and not source.is_symlink(), "source must be a regular directory")
    require(not archive.resolve().is_relative_to(source.resolve()), "archive must be outside source")
    required = {"parents", "hypothesis", "strategy"}
    require(required <= set(metadata) <= required | {"without_skill"}, "invalid candidate fields")
    require(type(metadata.get("without_skill", False)) is bool, "without_skill must be boolean")
    require(isinstance(metadata["parents"], list), "parents must be a list")
    for key in ("hypothesis", "strategy"):
        require(isinstance(metadata[key], str) and metadata[key].strip(), f"{key} is required")
    for parent in metadata["parents"]:
        candidate(archive, parent)
    files = file_digests(source)
    record = {"version": 1, "without_skill": False, **metadata, "files": files}
    ident = digest(record)
    destination = archive / "candidates" / ident
    if destination.exists():
        candidate(archive, ident)
        return ident
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        stage = Path(temporary) / "candidate"
        (stage / "files").mkdir(parents=True)
        for relative in files:
            target = stage / "files" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, target)
        require(file_digests(stage / "files") == files and file_digests(source) == files,
                "source changed during snapshot")
        write_new(stage / "candidate.json", record)
        stage.rename(destination)
    return ident


OBSERVATION_SURFACES = {"artifact", "tool_stdout", "tool_arguments", "assistant_message", "final_answer"}


def validate_contract(case):
    contract = case["contract"]
    require(isinstance(contract, dict) and set(contract) == {
        "source_prompt", "requirements", "reviewed_by", "review_note"}, "invalid case contract")
    for key in ("source_prompt", "review_note"):
        require(isinstance(contract[key], str) and contract[key].strip(), f"contract {key} required")
    identifier(contract["reviewed_by"])
    requirements = contract["requirements"]
    require(isinstance(requirements, list) and requirements, "contract requirements required")
    checks = {check["id"] for check in case["checks"]}
    covered = set()
    for requirement in requirements:
        require(isinstance(requirement, dict) and set(requirement) == {"text", "checks", "surfaces"},
                "invalid requirement fields")
        require(isinstance(requirement["text"], str) and requirement["text"].strip(), "requirement text required")
        require(requirement["text"] in contract["source_prompt"], "requirement missing from source")
        require(requirement["text"] in case["prompt"], "requirement missing from replay")
        targets = requirement["checks"]
        require(isinstance(targets, list) and targets and all(isinstance(c, str) for c in targets) and
                len(set(targets)) == len(targets), "invalid requirement checks")
        require(set(targets) <= checks, "requirement check is unknown")
        surfaces = requirement["surfaces"]
        require(isinstance(surfaces, list) and surfaces and all(isinstance(s, str) for s in surfaces) and
                len(set(surfaces)) == len(surfaces) and set(surfaces) <= OBSERVATION_SURFACES,
                "invalid observation surfaces")
        covered.update(targets)
    require(covered == checks, "every check needs an observation scope")


def validate_suite(suite: dict):
    require(set(suite) == {"version", "mode", "entrypoint", "cases"}, "invalid suite fields")
    require(type(suite["version"]) is int and suite["version"] in {1, 2}, "unsupported suite version")
    require(suite["mode"] in {"execution", "discovery"}, "invalid mode")
    entry = suite["entrypoint"]
    require(entry is None or (isinstance(entry, str) and entry and not Path(entry).is_absolute()
                             and ".." not in Path(entry).parts), "invalid entrypoint")
    require(isinstance(suite["cases"], list) and suite["cases"], "cases are required")
    ids = set()
    for case in suite["cases"]:
        fields = {"id", "prompt", "split", "checks"} | ({"contract"} if suite["version"] == 2 else set())
        require(set(case) == fields, "invalid case fields")
        identifier(case["id"])
        require(case["id"] not in ids, "duplicate case id")
        ids.add(case["id"])
        require(isinstance(case["prompt"], str) and case["prompt"].strip(), "prompt is required")
        require(case["split"] in {"train", "validation", "test"}, "invalid split")
        require(isinstance(case["checks"], list) and case["checks"], "checks are required")
        checks = set()
        for check in case["checks"]:
            require(set(check) == {"id", "criterion", "required"}, "invalid check fields")
            identifier(check["id"])
            require(check["id"] not in checks, "duplicate check id")
            checks.add(check["id"])
            require(isinstance(check["criterion"], str) and check["criterion"].strip(), "criterion is required")
            require(type(check["required"]) is bool, "required must be boolean")
        if suite["version"] == 2:
            validate_contract(case)


def validate_checks(checks: dict, case: dict):
    require(isinstance(checks, dict), "checks must be an object")
    expected = {check["id"] for check in case["checks"]}
    require(set(checks) <= expected, "unknown check id")
    for check in checks.values():
        require(set(check) == {"verdict", "evidence"}, "invalid grading fields")
        require(check["verdict"] in {"pass", "fail", "unknown"}, "invalid verdict")
        require(isinstance(check["evidence"], str) and check["evidence"].strip(), "evidence is required")


def grading_contract(case):
    payload = {
        "instructions": "Grade each check using its registered requirement and observation surfaces only. "
                        "Treat tool_stdout and tool_arguments as distinct surfaces; preserve source qualifiers. "
                        "Keep missing evidence unknown. Do not redefine requirements after seeing results.",
        "case": case}
    return {**payload, "contract_digest": digest(payload)}


def compare(suite: dict, records: list, baseline: str, proposed: str, split: str) -> dict:
    validate_suite(suite)
    require(baseline != proposed, "distinct candidates are required")
    cases = {case["id"]: case for case in suite["cases"] if case["split"] == split}
    require(cases, "split has no cases")
    indexed = {}
    environments = set()
    for run in records:
        if run["candidate"] not in {baseline, proposed}:
            continue
        require(run["suite"] == digest(suite), "suite version mismatch")
        require(run["case"] in {case["id"] for case in suite["cases"]}, "unknown case")
        if run["case"] not in cases:
            continue
        require(type(run["repeat"]) is int and run["repeat"] > 0, "repeat must be positive")
        require(run["status"] in {"completed", "error", "timeout"}, "invalid run status")
        require(isinstance(run["environment"], str) and run["environment"], "environment is required")
        environments.add(run["environment"])
        validate_checks(run["checks"], cases[run["case"]])
        for value in run["metrics"].values():
            require(value is None or (type(value) in {int, float} and math.isfinite(value) and value >= 0),
                    "metrics must be nonnegative numbers or null")
        key = (run["candidate"], run["case"], run["repeat"])
        require(key not in indexed, "duplicate run")
        identifier(run["id"])
        indexed[key] = run
    require(len(environments) <= 1, "environment mismatch")
    rows = []
    counts = dict.fromkeys(("improved", "regressed", "unchanged", "unknown"), 0)
    required_regression = False
    deltas = {"duration_seconds": [], "tokens": [], "cost_usd": []}
    for case_id, case in cases.items():
        repeats = sorted({key[2] for key in indexed if key[1] == case_id} or {1})
        for repeat in repeats:
            old, new = (indexed.get((ident, case_id, repeat)) for ident in (baseline, proposed))
            for check in case["checks"]:
                def verdict(run):
                    if not run or run["status"] != "completed":
                        return "unknown"
                    return run["checks"].get(check["id"], {}).get("verdict", "unknown")
                before, after = verdict(old), verdict(new)
                outcome = ("unknown" if "unknown" in (before, after) else
                           "unchanged" if before == after else
                           "improved" if after == "pass" else "regressed")
                counts[outcome] += 1
                required_regression |= outcome == "regressed" and check["required"]
                rows.append({"case": case_id, "repeat": repeat, "check": check["id"],
                             "baseline_run": old["id"] if old else None, "candidate_run": new["id"] if new else None,
                             "before": before, "after": after, "outcome": outcome})
            for metric in deltas:
                values = [run["metrics"].get(metric) if run and run["status"] == "completed" else None
                          for run in (old, new)]
                deltas[metric].append(None if None in values else values[1] - values[0])
    assessment = ("regressed" if required_regression else "inconclusive" if counts["unknown"] else
                  "tradeoff" if counts["regressed"] else "improved" if counts["improved"] else "unchanged")
    return {"baseline": baseline, "candidate": proposed, "suite": digest(suite), "split": split,
            "environment": next(iter(environments), None),
            "runs": sorted(run["id"] for run in indexed.values()),
            "run_digests": {run["id"]: digest(run) for run in indexed.values()},
            "assessment": assessment, "counts": counts, "rows": rows,
            "metrics": {key + "_delta": None if None in values else sum(values) / len(values)
                        for key, values in deltas.items()}}


def execute(archive, ident, suite, case_id, fixture, config, repeat=1, timeout=600):
    validate_suite(suite)
    require(suite["version"] == 2, "new execution requires a version 2 case contract")
    candidate_record = candidate(archive, ident)
    require(type(repeat) is int and repeat > 0, "repeat must be positive")
    require(type(timeout) in {int, float} and math.isfinite(timeout) and timeout > 0, "invalid timeout")
    required_config = {"model", "reasoning", "context"}
    require(required_config <= set(config) <= required_config | {"disabled_skills", "restricted"}, "invalid config fields")
    require(all(isinstance(config[key], str) and config[key].strip() for key in required_config), "config values are required")
    restricted = config.get("restricted")
    if "restricted" in config:
        require(isinstance(restricted, dict) and set(restricted) == {"executable"} and
                isinstance(restricted["executable"], str) and Path(restricted["executable"]).is_absolute(),
                "restricted requires an existing absolute executable")
    cli_program = restricted["executable"] if restricted else "codex"
    disabled = config.get("disabled_skills", [])
    require(isinstance(disabled, list) and all(isinstance(path, str) and Path(path).is_absolute()
                                             and Path(path).name == "SKILL.md" for path in disabled),
            "disabled_skills must contain absolute SKILL.md paths")
    config = {**config, "disabled_skills": sorted(set(disabled))}
    cases = [case for case in suite["cases"] if case["id"] == case_id]
    require(len(cases) == 1, "unknown case")
    case = cases[0]
    require(fixture.is_dir() and not fixture.is_symlink(), "fixture must be a regular directory")
    require(not archive.resolve().is_relative_to(fixture.resolve()), "archive must be outside fixture")
    fixture_files = file_digests(fixture)
    if restricted:
        with tempfile.TemporaryDirectory(prefix="skill-eval-version-") as version_temp:
            version_root = Path(version_temp)
            version_env, _ = restricted_runner.environments(version_root / "workspace", version_root, os.environ)
            Path(version_env["TMPDIR"]).mkdir()
            cli_version = subprocess.run([cli_program, "--version"], env=version_env,
                capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    else:
        cli_version = subprocess.run([cli_program, "--version"], capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    environment = {**config, "cli": cli_version, "fixture": fixture_files,
                   "sandbox": "workspace-write", "adapter": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if restricted:
        environment["sandbox"] = "workspace-only-named"
        environment["restricted_adapter"] = hashlib.sha256(Path(restricted_runner.__file__).read_bytes()).hexdigest()
    folder = archive.resolve() / "runs" / uuid.uuid4().hex
    folder.mkdir(parents=True)
    write_new(folder / "suite.json", suite)
    write_new(folder / "grading-contract.json", grading_contract(case))
    write_new(folder / "environment.json", environment)
    with tempfile.TemporaryDirectory(prefix="skill-eval-") as temporary:
        temporary = Path(temporary)
        work = temporary / "workspace"
        shutil.copytree(fixture, work, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        require(file_digests(work) == fixture_files, "fixture changed during copy")
        shutil.copytree(archive / "candidates" / ident / "files", work, dirs_exist_ok=True)
        prompt = case["prompt"]
        if suite["version"] == 2:
            scope = []
            for requirement in case["contract"]["requirements"]:
                item = {"requirement": requirement["text"], "surfaces": requirement["surfaces"]}
                if item not in scope:
                    scope.append(item)
            # Only source requirements and observation boundaries enter execution, never the rubric.
            prompt += "\n\nObservation scope for these requirements (fixed before execution):\n" + json.dumps(scope, ensure_ascii=False)
        entry = suite["entrypoint"]
        if suite["mode"] == "execution" and entry:
            if candidate_record["without_skill"]:
                require(not (work / entry).exists(), "without_skill candidate still contains entrypoint")
            else:
                require((work / entry).is_file(), "execution entrypoint is missing or not a file")
                prompt = f"Use the instructions in {entry} for this task.\n\n{prompt}"
        (folder / "prompt.txt").write_text(prompt, encoding="utf-8")
        answer = temporary / "answer.txt"
        command = ["codex", "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
                   "--json", "--color", "never", "-s", "workspace-write", "-m", config["model"],
                   "-c", "model_reasoning_effort=" + json.dumps(config["reasoning"]),
                   "-c", 'approval_policy="never"', "-C", str(work), "-o", str(answer), "-"]
        if config["disabled_skills"]:
            override = "skills.config=[" + ",".join(
                "{path=" + json.dumps(path) + ",enabled=false}" for path in config["disabled_skills"]) + "]"
            command[2:2] = ["-c", override]
        started = time.monotonic()
        status = "error"
        returncode = None
        process = None
        with (folder / "trace.jsonl").open("w") as out, (folder / "stderr.txt").open("w") as err:
            try:
                process_env = None
                if restricted:
                    settings, process_env = restricted_runner.prepare(cli_program, work, folder, os.environ, timeout)
                    # --sandbox would override the stricter named permission profile.
                    sandbox_index = command.index("-s")
                    del command[sandbox_index:sandbox_index + 2]
                    command[0] = cli_program
                    command[1:1] = ["--no-daemon"]
                    command[3:3] = ["--strict-config", *settings]
                write_new(folder / "command.json", command)
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=out, stderr=err,
                                           cwd=work, start_new_session=True, env=process_env)
                try:
                    process.communicate(prompt.encode(), timeout=remaining)
                    returncode = process.returncode
                    status = "completed" if returncode == 0 and answer.is_file() else "error"
                except subprocess.TimeoutExpired:
                    status = "timeout"
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                err.write(str(error))
            finally:
                if process is not None:
                    if process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    process.wait()
                    if process.stdin and not process.stdin.closed:
                        process.stdin.close()
                    returncode = process.returncode
        duration = time.monotonic() - started
        if answer.is_file():
            shutil.copy2(answer, folder / "answer.txt")
        # Generated symlinks are preserved, never followed when exporting artifacts.
        shutil.copytree(work, folder / "workspace", symlinks=True)
    tokens = 0
    measured = False
    for line in (folder / "trace.jsonl").read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        usage = event.get("usage", {}) if event.get("type") == "turn.completed" else {}
        values = [usage.get(key) for key in ("input_tokens", "output_tokens")]
        if all(type(value) is int and value >= 0 for value in values):
            tokens += sum(values)
            measured = True
    record = {"id": folder.name, "candidate": ident, "suite": digest(suite), "case": case_id, "repeat": repeat,
              "entrypoint": None if candidate_record["without_skill"] else entry,
              "environment": digest(environment), "status": status, "returncode": returncode,
              "checks": {}, "metrics": {"duration_seconds": duration, "tokens": tokens if measured else None, "cost_usd": None},
              "artifacts": artifact_digests(folder)}
    write_new(folder / "run.json", record)
    write_new(folder / "run-digest.json", digest(record))
    return folder


def artifact_digests(folder):
    result = {}
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder).as_posix()
        if relative in {"run.json", "run-digest.json", "grading.json"}:
            continue
        if path.is_symlink():
            result[relative] = {"link": os.readlink(path)}
        elif path.is_file():
            result[relative] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                "executable": bool(path.stat().st_mode & 0o111)}
    return result


def load_run(folder):
    record = read(folder / "run.json")
    require(record["id"] == folder.name, "run id mismatch")
    require(digest(record) == read(folder / "run-digest.json"), "run digest mismatch")
    require(artifact_digests(folder) == record["artifacts"], "artifact digest mismatch")
    packet = _grading_input(folder, record) if read(folder / "suite.json")["version"] == 2 else None
    if (folder / "grading.json").exists():
        grading = read(folder / "grading.json")
        require(grading["run_digest"] == digest(record), "grading run digest mismatch")
        if packet is not None:
            require(grading.get("contract_digest") == packet["contract_digest"],
                    "grading contract mismatch")
        record["checks"] = grading["checks"]
    return record


def grade(folder, grading):
    require(isinstance(grading, dict), "grading must be an object")
    record = load_run(folder)
    suite = read(folder / "suite.json")
    validate_suite(suite)
    fields = {"grader", "checks"}
    if suite["version"] == 2:
        require(grading.get("contract_digest") == grading_input(folder)["contract_digest"],
                "grading contract mismatch; use the frozen grading-input packet")
        fields.add("contract_digest")
    require(set(grading) == fields, "invalid grading fields")
    require(isinstance(grading["grader"], str) and grading["grader"].strip(), "grader is required")
    case = next(case for case in suite["cases"] if case["id"] == record["case"])
    validate_checks(grading["checks"], case)
    require(set(grading["checks"]) == {check["id"] for check in case["checks"]}, "all checks must be graded")
    write_new(folder / "grading.json", {**grading, "run_digest": digest(record)})


def grading_input(folder):
    """Export the run's frozen case for a grader, without candidate names or proposed changes."""
    return _grading_input(folder, load_run(folder))


def _grading_input(folder, record):
    suite = read(folder / "suite.json")
    validate_suite(suite)
    require(suite["version"] == 2, "legacy run has no pre-execution contract")
    require(record["suite"] == digest(suite), "suite digest mismatch")
    case = next(case for case in suite["cases"] if case["id"] == record["case"])
    require((folder / "grading-contract.json").is_file(), "missing frozen grading contract")
    packet = read(folder / "grading-contract.json")
    require(set(packet) == {"instructions", "case", "contract_digest"} and packet["case"] == case,
            "frozen grading contract mismatch")
    require(isinstance(packet["instructions"], str) and packet["instructions"].strip() and
            packet["contract_digest"] == digest({k: v for k, v in packet.items() if k != "contract_digest"}),
            "frozen grading contract digest mismatch")
    return packet


def report(folders, comparison):
    require(sorted(path.name for path in folders) == sorted(comparison["runs"]), "report run selection mismatch")
    require({path.name: digest(load_run(path)) for path in folders} == comparison["run_digests"],
            "report run digest mismatch")
    sections = []
    for folder in folders:
        record = load_run(folder)
        answer = (folder / "answer.txt").read_text(encoding="utf-8") if (folder / "answer.txt").exists() else "(no answer)"
        prompt = (folder / "prompt.txt").read_text(encoding="utf-8")
        summary = {key: record[key] for key in ("case", "repeat", "status", "metrics", "checks")}
        sections.append(f'<section><h2>{html.escape(record["case"])} / {html.escape(folder.name[:8])}</h2>'
                        f'<h3>依頼</h3><pre>{html.escape(prompt)}</pre>'
                        f'<h3>成果物</h3><pre>{html.escape(answer)}</pre>'
                        f'<h3>採点と測定</h3><pre>{html.escape(json.dumps(summary, ensure_ascii=False, indent=2))}</pre>'
                        f'<details><summary>実行記録と版</summary><pre>{html.escape(json.dumps(record, ensure_ascii=False, indent=2))}</pre></details>'
                        f'<p><a href="{html.escape((folder / "workspace").as_uri(), quote=True)}">作業結果のフォルダ</a></p>'
                        f'<label>評価コメント<textarea data-run="{html.escape(folder.name, quote=True)}"></textarea></label></section>')
    return ('<!doctype html><html lang="ja"><meta charset="utf-8"><title>Skill 評価</title>'
            '<style>body{max-width:1000px;margin:40px auto;font:16px system-ui;padding:0 20px}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f7;padding:16px}'
            'textarea{display:block;width:100%;min-height:90px}section{margin:40px 0}button{padding:12px}</style>'
            '<h1>Skill 評価</h1><p>この比較は観測結果です。採用判断と統計的な確実性は別に評価します。</p>'
            f'<pre>{html.escape(json.dumps(comparison, ensure_ascii=False, indent=2))}</pre>'
            + ''.join(sections) + '<button id="save">コメントを JSON へ保存</button>'
            '<script>document.getElementById("save").onclick=()=>{'
            'const reviews=[...document.querySelectorAll("textarea")].map(e=>({run:e.dataset.run,comment:e.value}));'
            'const u=URL.createObjectURL(new Blob([JSON.stringify({reviews},null,2)],{type:"application/json"}));'
            'const a=document.createElement("a");a.href=u;a.download="feedback.json";a.click();'
            'setTimeout(()=>URL.revokeObjectURL(u),1000);};</script></html>')


def remember(archive, note):
    require(set(note) == {"hypothesis", "scope", "status", "support", "counterevidence", "directions"},
            "invalid diagnosis fields")
    for key in ("hypothesis", "scope"):
        require(isinstance(note[key], str) and note[key].strip(), f"{key} is required")
    require(note["status"] in {"active", "refuted"}, "invalid diagnosis status")
    evidence = {}
    for key in ("support", "counterevidence"):
        require(isinstance(note[key], list), "evidence references must be lists")
        for run_id in note[key]:
            folder = archive / "runs" / identifier(run_id)
            record = load_run(folder)
            suite = read(folder / "suite.json")
            case = next(case for case in suite["cases"] if case["id"] == record["case"])
            require(case["split"] == "train", "momentum accepts train evidence only")
            require(record["status"] == "completed" and record["checks"], "graded completed evidence is required")
            evidence[run_id] = digest(record)
    require(evidence, "execution evidence is required")
    require(isinstance(note["directions"], list) and note["directions"], "directions are required")
    for direction in note["directions"]:
        require(set(direction) == {"operation", "layer", "path", "reason"}, "invalid direction fields")
        require(direction["operation"] in {"add", "delete", "replace", "move"}, "invalid operation")
        require(direction["layer"] in {"metadata", "body", "reference", "script", "configuration"}, "invalid layer")
        for key in ("path", "reason"):
            require(isinstance(direction[key], str) and direction[key].strip(), f"{key} is required")
        require(not Path(direction["path"]).is_absolute() and ".." not in Path(direction["path"]).parts, "invalid direction path")
    record = {"version": 1, **note, "evidence_digests": evidence}
    ident = digest(record)
    path = archive / "diagnoses" / (ident + ".json")
    if path.exists():
        require(read(path) == record, "diagnosis digest mismatch")
    else:
        write_new(path, record)
    return ident


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snap = commands.add_parser("snapshot", help="archive a candidate bundle without changing its source")
    snap.add_argument("--archive", type=Path, required=True)
    snap.add_argument("--source", type=Path, required=True)
    snap.add_argument("--metadata", type=Path, required=True)
    run = commands.add_parser("run", help="execute one case using the Codex CLI")
    run.add_argument("--archive", type=Path, required=True)
    run.add_argument("--candidate", required=True)
    run.add_argument("--suite", type=Path, required=True)
    run.add_argument("--case", required=True)
    run.add_argument("--fixture", type=Path, required=True)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--repeat", type=int, default=1)
    run.add_argument("--timeout", type=float, default=600)
    grading = commands.add_parser("grade", help="attach independent, evidence-backed grading")
    grading.add_argument("--run", type=Path, required=True)
    grading.add_argument("--grading", type=Path, required=True)
    packet = commands.add_parser("grading-input", help="export frozen requirements and observation scopes")
    packet.add_argument("--run", type=Path, required=True)
    packet.add_argument("--output", type=Path, required=True)
    comp = commands.add_parser("compare", help="compare paired runs; never promotes a candidate")
    comp.add_argument("--suite", type=Path, required=True)
    comp.add_argument("--runs", nargs="+", type=Path, required=True)
    comp.add_argument("--baseline", required=True)
    comp.add_argument("--candidate", required=True)
    comp.add_argument("--split", choices=["train", "validation", "test"], required=True)
    comp.add_argument("--output", type=Path, required=True)
    view = commands.add_parser("report", help="create a static review page with feedback export")
    view.add_argument("--runs", nargs="+", type=Path, required=True)
    view.add_argument("--comparison", type=Path, required=True)
    view.add_argument("--output", type=Path, required=True)
    memory = commands.add_parser("remember", help="archive training diagnoses and counterevidence")
    memory.add_argument("--archive", type=Path, required=True)
    memory.add_argument("--diagnosis", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "snapshot":
            print(snapshot(args.archive, args.source, read(args.metadata)))
        elif args.command == "run":
            print(execute(args.archive, args.candidate, read(args.suite), args.case, args.fixture,
                          read(args.config), args.repeat, args.timeout))
        elif args.command == "grade":
            grade(args.run, read(args.grading))
            print(args.run / "grading.json")
        elif args.command == "grading-input":
            require(not args.output.resolve().is_relative_to(args.run.resolve()),
                    "grading-input output must be outside the run archive")
            write_new(args.output, grading_input(args.run))
            print(args.output)
        elif args.command == "compare":
            result = compare(read(args.suite), [load_run(path) for path in args.runs],
                             args.baseline, args.candidate, args.split)
            write_new(args.output, result)
            print(args.output)
        elif args.command == "report":
            rendered = report([path.resolve() for path in args.runs], read(args.comparison))
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
            print(args.output)
        else:
            print(remember(args.archive, read(args.diagnosis)))
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
