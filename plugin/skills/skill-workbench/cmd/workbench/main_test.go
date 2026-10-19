package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"testing"
	"time"
)

type experiment struct{ root, archive, source string }

func setup(t *testing.T) experiment {
	t.Helper()
	root := t.TempDir()
	source := filepath.Join(root, "source")
	must(os.Mkdir(source, 0755))
	must(os.WriteFile(filepath.Join(source, "SKILL.md"), []byte("original"), 0644))
	return experiment{root, filepath.Join(root, "archive"), source}
}
func metadata(parents ...string) object {
	p := []any{}
	for _, id := range parents {
		p = append(p, id)
	}
	return object{"parents": p, "hypothesis": "Remove forced review", "strategy": "minimal"}
}
func suite() object {
	return object{"version": 1, "mode": "execution", "entrypoint": "SKILL.md", "cases": []any{object{"id": "small-fix", "prompt": "Fix the typo", "split": "validation", "checks": []any{object{"id": "complete", "criterion": "Requested typo is fixed", "required": true}}}}}
}
func runRecord(id, verdict, status string, repeat int) object {
	return object{"id": fmt.Sprintf("%s-%d", id, repeat), "candidate": id, "suite": digest(suite()), "case": "small-fix", "repeat": repeat, "environment": "same-environment", "status": status, "checks": object{"complete": object{"verdict": verdict, "evidence": "output inspected"}}, "metrics": object{"duration_seconds": 10, "tokens": nil}}
}
func expectFailure(t *testing.T, fragment string, f func()) {
	t.Helper()
	defer func() {
		e := recover()
		if e == nil {
			t.Errorf("expected failure containing %q", fragment)
		} else if !strings.Contains(fmt.Sprint(e), fragment) {
			t.Errorf("failure = %v; want %q", e, fragment)
		}
	}()
	f()
}
func fakeCodex(t *testing.T, x experiment, body string) {
	t.Helper()
	bin := filepath.Join(x.root, "bin")
	must(os.MkdirAll(bin, 0755))
	script := `#!/bin/sh
if [ "$1" = --version ]; then echo 'test-codex 1'; exit 0; fi
while [ "$#" -gt 0 ]; do
 if [ "$1" = '-o' ]; then shift; answer="$1"; fi
 shift
done
` + body
	must(os.WriteFile(filepath.Join(bin, "codex"), []byte(script), 0755))
	t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
}

const answerBody = `printf 'finished' > "$answer"
`

func executeTest(t *testing.T, x experiment, body string, s object, timeout float64, config object) string {
	t.Helper()
	fakeCodex(t, x, body)
	id := snapshot(x.archive, x.source, metadata())
	fixture := filepath.Join(x.root, "fixture")
	must(os.MkdirAll(fixture, 0755))
	if config == nil {
		config = object{"model": "test-model", "reasoning": "low", "context": "test context"}
	}
	return execute(x.archive, id, s, "small-fix", fixture, config, 1, timeout)
}
func grading() object {
	return object{"grader": "independent", "checks": object{"complete": object{"verdict": "fail", "evidence": "answer.txt contains no requested change"}}}
}
func diagnosis(id string) object {
	return object{"hypothesis": "Forced review delays the fix", "scope": "small fixes", "status": "active", "support": []any{id}, "counterevidence": []any{}, "directions": []any{object{"operation": "delete", "layer": "body", "path": "SKILL.md", "reason": "Remove unneeded review"}}}
}

func TestSnapshotPreservesParentsAndOriginalFiles(t *testing.T) {
	x := setup(t)
	parent := snapshot(x.archive, x.source, metadata())
	must(os.WriteFile(filepath.Join(x.source, "SKILL.md"), []byte("revised"), 0644))
	child := snapshot(x.archive, x.source, metadata(parent))
	if parent == child {
		t.Fatal("edited candidate reused parent ID")
	}
	b, e := os.ReadFile(filepath.Join(x.archive, "candidates", parent, "files", "SKILL.md"))
	must(e)
	if string(b) != "original" {
		t.Errorf("parent changed: %s", b)
	}
	if !same(candidate(x.archive, child)["parents"], []any{parent}) {
		t.Error("parent relationship lost")
	}
}
func TestSnapshotRejectsSymbolicLinks(t *testing.T) {
	x := setup(t)
	must(os.Symlink(x.root, filepath.Join(x.source, "linked")))
	expectFailure(t, "symbolic", func() { snapshot(x.archive, x.source, metadata()) })
}
func TestCandidateDetectsModifiedArchive(t *testing.T) {
	x := setup(t)
	id := snapshot(x.archive, x.source, metadata())
	must(os.WriteFile(filepath.Join(x.archive, "candidates", id, "files", "SKILL.md"), []byte("tampered"), 0644))
	expectFailure(t, "digest", func() { candidate(x.archive, id) })
}
func TestCompareReportsPairedImprovementsWithMissingMetrics(t *testing.T) {
	r := compare(suite(), []object{runRecord("old", "fail", "completed", 1), runRecord("new", "pass", "completed", 1)}, "old", "new", "validation")
	if r["assessment"] != "improved" || !same(r["counts"], object{"improved": 1, "regressed": 0, "unchanged": 0, "unknown": 0}) {
		t.Errorf("unexpected comparison: %s", encoded(r, true))
	}
	if obj(r["metrics"])["tokens_delta"] != nil {
		t.Error("missing tokens reported as measured")
	}
}
func TestCompareKeepsErrorsAndMissingPairsUnknown(t *testing.T) {
	r := compare(suite(), []object{runRecord("old", "pass", "completed", 1), runRecord("new", "pass", "error", 1), runRecord("new", "pass", "completed", 2)}, "old", "new", "validation")
	if r["assessment"] != "inconclusive" || obj(r["counts"])["unknown"] != 2 {
		t.Errorf("unexpected comparison: %v", r)
	}
}
func TestCompareBlocksRequiredRegressionDespiteImprovement(t *testing.T) {
	r := compare(suite(), []object{runRecord("old", "fail", "completed", 1), runRecord("new", "pass", "completed", 1), runRecord("old", "pass", "completed", 2), runRecord("new", "fail", "completed", 2)}, "old", "new", "validation")
	if r["assessment"] != "regressed" {
		t.Errorf("assessment = %v", r["assessment"])
	}
}
func TestCompareRejectsMixedEnvironments(t *testing.T) {
	old, new := runRecord("old", "pass", "completed", 1), runRecord("new", "pass", "completed", 1)
	new["environment"] = "other"
	expectFailure(t, "environment", func() { compare(suite(), []object{old, new}, "old", "new", "validation") })
}
func TestCompareRejectsMissingEvidence(t *testing.T) {
	old, new := runRecord("old", "pass", "completed", 1), runRecord("new", "pass", "completed", 1)
	obj(obj(new["checks"])["complete"])["evidence"] = ""
	expectFailure(t, "evidence", func() { compare(suite(), []object{old, new}, "old", "new", "validation") })
}
func TestSuiteRejectsDuplicateCaseIDs(t *testing.T) {
	s := suite()
	s["cases"] = append(array(s["cases"]), array(s["cases"])[0])
	expectFailure(t, "duplicate", func() { validateSuite(s) })
}
func TestExecuteSavesOutputsAndUsageWithoutGrading(t *testing.T) {
	x := setup(t)
	folder := executeTest(t, x, answerBody+`echo '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":3}}'
`, suite(), 5, nil)
	r := loadRun(folder)
	if r["status"] != "completed" || !same(obj(r["metrics"])["tokens"], 13) || len(obj(r["checks"])) != 0 {
		t.Errorf("run = %s", encoded(r, true))
	}
	answer, e := os.ReadFile(filepath.Join(folder, "answer.txt"))
	must(e)
	if string(answer) != "finished" {
		t.Errorf("answer = %s", answer)
	}
	prompt, e := os.ReadFile(filepath.Join(folder, "prompt.txt"))
	must(e)
	if strings.Contains(string(prompt), "Requested typo is fixed") {
		t.Error("grading criteria leaked to execution prompt")
	}
	if _, e = os.Stat(filepath.Join(x.source, "SKILL.md")); e != nil {
		t.Fatal(e)
	}
}
func TestExecuteRecordsTimeoutAndKillsProcessGroup(t *testing.T) {
	x := setup(t)
	pidFile := filepath.Join(x.root, "child.pid")
	body := fmt.Sprintf("sleep 30 &\necho $! > %q\nwait\n", pidFile)
	folder := executeTest(t, x, body, suite(), 0.15, nil)
	if loadRun(folder)["status"] != "timeout" {
		t.Error("timeout was not recorded")
	}
	b, e := os.ReadFile(pidFile)
	must(e)
	var pid int
	_, e = fmt.Sscan(string(b), &pid)
	must(e)
	deadline := time.Now().Add(2 * time.Second)
	for syscall.Kill(pid, 0) == nil && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if syscall.Kill(pid, 0) == nil {
		t.Errorf("child %d survived timeout", pid)
	}
}
func TestGradeRejectsModifiedArtifacts(t *testing.T) {
	x := setup(t)
	folder := executeTest(t, x, answerBody, suite(), 5, nil)
	must(os.WriteFile(filepath.Join(folder, "answer.txt"), []byte("modified"), 0644))
	expectFailure(t, "digest", func() { grade(folder, grading()) })
}
func TestReportShowsGradedArtifactsAndEscapesHTML(t *testing.T) {
	x := setup(t)
	folder := executeTest(t, x, `printf '<script>bad</script>' > "$answer"
`, suite(), 5, nil)
	grade(folder, grading())
	r := loadRun(folder)
	page := report([]string{folder}, object{"assessment": "unchanged", "runs": []any{filepath.Base(folder)}, "run_digests": object{filepath.Base(folder): digest(r)}})
	if obj(obj(r["checks"])["complete"])["verdict"] != "fail" {
		t.Error("grading lost")
	}
	if !strings.Contains(page, "&lt;script&gt;bad&lt;/script&gt;") || strings.Contains(page, "<script>bad</script>") {
		t.Error("HTML response not escaped")
	}
	if !strings.Contains(page, `data-run="`+filepath.Base(folder)+`"`) {
		t.Error("feedback export lost run identity")
	}
}
func TestDiagnosisRejectsHeldOutEvidence(t *testing.T) {
	x := setup(t)
	folder := executeTest(t, x, answerBody, suite(), 5, nil)
	expectFailure(t, "train", func() { remember(x.archive, diagnosis(filepath.Base(folder))) })
}
func TestExecuteDisablesSkillsOnlyForEvaluationProcess(t *testing.T) {
	x := setup(t)
	folder := executeTest(t, x, answerBody, suite(), 5, object{"model": "test-model", "reasoning": "low", "context": "test", "disabled_skills": []any{"/tmp/global/SKILL.md", "/tmp/global/SKILL.md"}})
	command := array(read(filepath.Join(folder, "command.json")))
	found := false
	for _, v := range command {
		found = found || v == `skills.config=[{path="/tmp/global/SKILL.md",enabled=false}]`
	}
	if !found {
		t.Errorf("command = %v", command)
	}
	if !same(obj(read(filepath.Join(folder, "environment.json")))["disabled_skills"], []any{"/tmp/global/SKILL.md"}) {
		t.Error("disabled skills not recorded canonically")
	}
}
func TestGradeRejectsOverwritingPriorJudgment(t *testing.T) {
	x := setup(t)
	folder := executeTest(t, x, answerBody, suite(), 5, nil)
	grade(folder, grading())
	expectFailure(t, "exist", func() { grade(folder, grading()) })
}
func TestRememberPreservesGradedTrainingEvidence(t *testing.T) {
	x := setup(t)
	s := suite()
	obj(array(s["cases"])[0])["split"] = "train"
	folder := executeTest(t, x, answerBody, s, 5, nil)
	grade(folder, grading())
	id := remember(x.archive, diagnosis(filepath.Base(folder)))
	saved := obj(read(filepath.Join(x.archive, "diagnoses", id+".json")))
	if !same(saved["support"], []any{filepath.Base(folder)}) || obj(saved["evidence_digests"])[filepath.Base(folder)] != digest(loadRun(folder)) {
		t.Error("graded training evidence not preserved")
	}
	if remember(x.archive, diagnosis(filepath.Base(folder))) != id {
		t.Error("idempotent diagnosis changed ID")
	}
}
func TestExecuteRejectsMissingDeclaredEntrypoint(t *testing.T) {
	x := setup(t)
	s := suite()
	s["entrypoint"] = "missing/SKILL.md"
	expectFailure(t, "entrypoint", func() { executeTest(t, x, answerBody, s, 5, nil) })
}
func TestSnapshotRejectsSpecialFilesAndPreservesExistingArchive(t *testing.T) {
	x := setup(t)
	first := snapshot(x.archive, x.source, metadata()) // A FIFO is rejected before reading; no partial candidate is published.
	must(syscall.Mkfifo(filepath.Join(x.source, "pipe"), 0600))
	expectFailure(t, "regular", func() { snapshot(x.archive, x.source, metadata()) })
	if candidate(x.archive, first)["hypothesis"] != "Remove forced review" {
		t.Error("prior candidate changed")
	}
}
func TestLoadRunRejectsChangedArtifactExecutability(t *testing.T) {
	x := setup(t)
	folder := executeTest(t, x, answerBody, suite(), 5, nil)
	must(os.Chmod(filepath.Join(folder, "answer.txt"), 0755))
	expectFailure(t, "digest", func() { loadRun(folder) })
}
func TestExecuteRecordsEmbeddedAdapterRevision(t *testing.T) {
	x := setup(t)
	folder := executeTest(t, x, answerBody, suite(), 5, nil)
	if obj(read(filepath.Join(folder, "environment.json")))["adapter"] != hash(adapterSource) {
		t.Error("adapter revision is not source digest")
	}
}
func TestCompareRecordsExactTrialsAndEnvironment(t *testing.T) {
	r := compare(suite(), []object{runRecord("old", "pass", "completed", 1), runRecord("new", "pass", "completed", 1)}, "old", "new", "validation")
	row := obj(array(r["rows"])[0])
	if row["baseline_run"] != "old-1" || row["candidate_run"] != "new-1" || r["environment"] != "same-environment" {
		t.Errorf("comparison lost trial identity: %v", r)
	}
}
func TestExecuteReapsProcessAfterBrokenPipeTimeout(t *testing.T) {
	x := setup(t)
	s := suite()
	obj(array(s["cases"])[0])["prompt"] = strings.Repeat("x", 2*1024*1024)
	pidFile := filepath.Join(x.root, "pid")
	body := fmt.Sprintf("echo $$ > %q\nexec 0<&-\nsleep 30\n", pidFile)
	started := time.Now()
	folder := executeTest(t, x, body, s, 0.15, nil)
	if loadRun(folder)["status"] != "timeout" {
		t.Error("broken pipe timeout not recorded")
	}
	if time.Since(started) > 3*time.Second {
		t.Error("timeout did not terminate promptly")
	}
	b, e := os.ReadFile(pidFile)
	must(e)
	var pid int
	_, e = fmt.Sscan(string(b), &pid)
	must(e)
	if syscall.Kill(pid, 0) == nil {
		t.Errorf("process %d survived timeout", pid)
	}
}
func TestExecuteAllowsExplicitWithoutSkillCandidate(t *testing.T) {
	x := setup(t)
	fakeCodex(t, x, answerBody)
	must(os.Remove(filepath.Join(x.source, "SKILL.md")))
	m := metadata()
	m["without_skill"] = true
	id := snapshot(x.archive, x.source, m)
	fixture := filepath.Join(x.root, "fixture")
	must(os.Mkdir(fixture, 0755))
	folder := execute(x.archive, id, suite(), "small-fix", fixture, object{"model": "test", "reasoning": "low", "context": "test"}, 1, 5)
	r := loadRun(folder)
	prompt, e := os.ReadFile(filepath.Join(folder, "prompt.txt"))
	must(e)
	if r["status"] != "completed" || r["entrypoint"] != nil || strings.Contains(string(prompt), "Use the instructions") {
		t.Error("without_skill incorrectly injected instructions")
	}
}
func TestDigestPreservesPythonStoredIDs(t *testing.T) {
	v := object{"日本語": "<&>\u2028", "a": []any{json.Number("1"), json.Number("1.0"), json.Number("0.00001"), json.Number("1e16"), true, nil}}
	want := `{"a": [1, 1.0, 1e-05, 1e+16, true, null], "日本語": "<&> "}`
	if canonical(v) != want {
		t.Errorf("canonical = %s; want %s", canonical(v), want)
	}
}
func TestGeneratedSymlinksAreExportedWithoutFollowingTargets(t *testing.T) {
	x := setup(t)
	secret := filepath.Join(x.root, "outside.txt")
	must(os.WriteFile(secret, []byte("private"), 0644))
	folder := executeTest(t, x, answerBody+fmt.Sprintf("ln -s %q linked\n", secret), suite(), 5, nil)
	r := loadRun(folder)
	if obj(obj(r["artifacts"])["workspace/linked"])["link"] != secret {
		t.Error("generated link not preserved")
	}
	if _, ok := obj(r["artifacts"])["workspace/linked/outside.txt"]; ok {
		t.Error("generated link followed")
	}
}

func captureCLIError(t *testing.T, args []string) (int, string) {
	t.Helper()
	file, err := os.CreateTemp(t.TempDir(), "stderr-")
	if err != nil {
		t.Fatal(err)
	}
	previous := os.Stderr
	os.Stderr = file
	defer func() { os.Stderr = previous; file.Close() }()
	code := cli(args)
	data, err := os.ReadFile(file.Name())
	if err != nil {
		t.Fatal(err)
	}
	return code, string(data)
}
func TestCLIRejectsInvalidArgumentsWithUsageAndExitTwo(t *testing.T) {
	for _, args := range [][]string{nil, {"unknown"}, {"unknown", "--help"}, {"snapshot"}, {"run", "--unknown", "value"}, {"snapshot", "--archive"}} {
		code, stderr := captureCLIError(t, args)
		if code != 2 || !strings.HasPrefix(stderr, "usage:") || !strings.Contains(stderr, "error:") {
			t.Errorf("cli(%v) = %d, %q; want usage/plain error and exit 2", args, code, stderr)
		}
	}
}
func TestCLIOperationValidationFailureReturnsJSONAndExitOne(t *testing.T) {
	x := setup(t)
	metadataPath := filepath.Join(x.root, "invalid.json")
	writeNew(metadataPath, object{})
	code, stderr := captureCLIError(t, []string{"snapshot", "--archive", x.archive, "--source", x.source, "--metadata", metadataPath})
	var failure object
	if err := json.Unmarshal([]byte(stderr), &failure); err != nil {
		t.Fatalf("stderr is not JSON: %q", stderr)
	}
	if code != 1 || !nonempty(failure["error"]) {
		t.Errorf("operation validation = %d, %v; want JSON error and exit 1", code, failure)
	}
}
func TestCLISnapshotWritesExistingPythonCompatibleCandidateID(t *testing.T) {
	x := setup(t)
	meta := filepath.Join(x.root, "metadata.json")
	writeNew(meta, metadata())
	if code := cli([]string{"snapshot", "--archive=" + x.archive, "--source", x.source, "--metadata", meta}); code != 0 {
		t.Fatalf("snapshot exit = %d", code)
	}
	id := snapshot(x.archive, x.source, metadata())
	// This digest is generated by the original Python implementation for the same bytes.
	const want = "7d1c7ea356da74ebe12200cd2f91b88a1124a0ac0946824d4818292fffcf579d"
	if id != want {
		t.Errorf("candidate ID = %s; want %s", id, want)
	}
}

func TestSnapshotRejectsSourceGrowthDuringCopy(t *testing.T) {
	x := setup(t)
	// コピーが始まったことを staging directory で確認し、入力の増加を再現する。
	for i := 0; i < 300; i++ {
		must(os.WriteFile(filepath.Join(x.source, fmt.Sprintf("reference-%03d.md", i)), []byte(strings.Repeat("x", 1024)), 0644))
	}
	stop := make(chan struct{})
	done := make(chan struct{})
	defer func() { close(stop); <-done }()
	go func() {
		defer close(done)
		for {
			select {
			case <-stop:
				return
			default:
			}
			paths, _ := filepath.Glob(filepath.Join(x.archive, "candidates", "snapshot-*", "candidate", "files"))
			if len(paths) > 0 {
				_ = os.WriteFile(filepath.Join(x.source, "new-reference.md"), []byte("new requirement"), 0644)
				return
			}
			runtime.Gosched()
		}
	}()
	expectFailure(t, "source changed", func() { snapshot(x.archive, x.source, metadata()) })
}
func TestRunModifiesOnlyItsTemporaryWorkspace(t *testing.T) {
	x := setup(t)
	fixture := filepath.Join(x.root, "fixture")
	must(os.Mkdir(fixture, 0755))
	must(os.WriteFile(filepath.Join(fixture, "input.txt"), []byte("fixture"), 0644))
	folder := executeTest(t, x, answerBody+"printf changed > SKILL.md\nprintf changed > input.txt\n", suite(), 5, nil)
	for path, want := range map[string]string{filepath.Join(x.source, "SKILL.md"): "original", filepath.Join(fixture, "input.txt"): "fixture"} {
		b, e := os.ReadFile(path)
		must(e)
		if string(b) != want {
			t.Errorf("input changed: %s", path)
		}
	}
	b, e := os.ReadFile(filepath.Join(folder, "workspace", "input.txt"))
	must(e)
	if string(b) != "changed" {
		t.Error("generated workspace was not retained")
	}
}

func TestSuiteAcceptsPythonEquivalentVersionWithoutChangingDigest(t *testing.T) {
	for _, version := range []any{json.Number("1.0"), true} {
		t.Run(fmt.Sprint(version), func(t *testing.T) {
			s := suite()
			s["version"] = version
			before := digest(s)
			defer func() {
				if e := recover(); e != nil {
					t.Fatalf("Python-compatible version rejected: %v", e)
				}
			}()
			validateSuite(s)
			if digest(s) != before || s["version"] != version {
				t.Error("validation normalized stored version/digest")
			}
		})
	}
}
func TestExecuteRejectsSymlinkAnswerWithoutReadingTarget(t *testing.T) {
	x := setup(t)
	target := filepath.Join(x.root, "outside.txt")
	must(os.WriteFile(target, []byte("outside private answer"), 0644))
	folder := executeTest(t, x, fmt.Sprintf("ln -s %q \"$answer\"\n", target), suite(), 5, nil)
	record := loadRun(folder)
	if record["status"] != "error" {
		t.Errorf("symlink answer status = %v; want error", record["status"])
	}
	if exists(filepath.Join(folder, "answer.txt")) {
		t.Error("symlink target exported as answer")
	}
	if _, ok := obj(record["artifacts"])["answer.txt"]; ok {
		t.Error("symlink answer included in artifacts")
	}
}
func TestExecutePreservesPythonBrokenPipeSuccess(t *testing.T) {
	x := setup(t)
	s := suite()
	obj(array(s["cases"])[0])["prompt"] = strings.Repeat("x", 2*1024*1024)
	folder := executeTest(t, x, answerBody+"exec 0<&-\nexit 0\n", s, 5, nil)
	record := loadRun(folder)
	if record["status"] != "completed" || !same(record["returncode"], 0) {
		t.Errorf("early stdin close = %v/%v; Python communicate suppresses EPIPE", record["status"], record["returncode"])
	}
}
func TestExecuteRecordsStartFailureAfterVersionProbe(t *testing.T) {
	x := setup(t)
	bin := filepath.Join(x.root, "bin")
	must(os.Mkdir(bin, 0755))
	executable := filepath.Join(bin, "codex")
	must(os.WriteFile(executable, []byte("#!/bin/sh\nif [ \"$1\" = --version ]; then /bin/rm -- \"$0\"; echo test-codex; exit 0; fi\nexit 99\n"), 0755))
	t.Setenv("PATH", bin)
	id := snapshot(x.archive, x.source, metadata())
	fixture := filepath.Join(x.root, "fixture")
	must(os.Mkdir(fixture, 0755))
	folder := execute(x.archive, id, suite(), "small-fix", fixture, object{"model": "test", "reasoning": "low", "context": "test"}, 1, 5)
	record := loadRun(folder)
	if record["status"] != "error" || record["returncode"] != nil {
		t.Errorf("Start failure = %v/%v; want error/null", record["status"], record["returncode"])
	}
	if len(obj(record["artifacts"])) == 0 {
		t.Error("Start failure did not preserve run artifacts")
	}
}

type failingInput struct{}

func (failingInput) Write([]byte) (int, error) { return 0, syscall.EIO }
func (failingInput) Close() error              { return nil }
func TestCommunicationReapsProcessOnNonBrokenPipeWriteFailure(t *testing.T) {
	cmd := exec.Command("/bin/sh", "-c", "sleep 30")
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { _ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL) }()
	timedOut, waitErr, writeErr := communicate(cmd, failingInput{}, "prompt", time.Second)
	if timedOut || waitErr == nil || !errors.Is(writeErr, syscall.EIO) {
		t.Errorf("communication = timeout %v, wait %v, write %v", timedOut, waitErr, writeErr)
	}
	if syscall.Kill(cmd.Process.Pid, 0) == nil {
		t.Error("process survived non-EPIPE communication failure")
	}
}

type heldInput struct{ started, release chan struct{} }

func (w heldInput) Write(p []byte) (int, error) { close(w.started); <-w.release; return 0, syscall.EIO }
func (w heldInput) Close() error                { return nil }
func TestCommunicationWaitsForWriterEvenAfterProcessExit(t *testing.T) {
	cmd := exec.Command("/bin/sh", "-c", "exit 0")
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	writer := heldInput{make(chan struct{}), make(chan struct{})}
	done := make(chan error, 1)
	go func() { _, _, writeErr := communicate(cmd, writer, "prompt", time.Second); done <- writeErr }()
	<-writer.started
	// 親 process が reap されてからも writer が終わるまで結果を返さない。
	deadline := time.Now().Add(time.Second)
	for syscall.Kill(cmd.Process.Pid, 0) == nil && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	if syscall.Kill(cmd.Process.Pid, 0) == nil {
		close(writer.release)
		<-done
		t.Fatal("test process was not reaped")
	}
	select {
	case <-done:
		close(writer.release)
		t.Fatal("returned before stdin writer completed")
	default:
	}
	close(writer.release)
	if err := <-done; !errors.Is(err, syscall.EIO) {
		t.Errorf("writer failure lost after process exit: %v", err)
	}
}
