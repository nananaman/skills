package review

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"syscall"
	"testing"
)

type fixture struct {
	t                        *testing.T
	root, repo, runs, roster string
}
type response struct {
	code        int
	out, stderr string
}

func newFixture(t *testing.T) *fixture {
	t.Helper()
	root, err := canonical(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	f := &fixture{t: t, root: root, repo: filepath.Join(root, "repo"), runs: filepath.Join(root, "runs"), roster: filepath.Join(root, "roster.json")}
	f.gitAt(root, "init", "-q", f.repo)
	f.git("config", "user.name", "Review Test")
	f.git("config", "user.email", "review-test@example.com")
	f.write(filepath.Join(f.repo, "example.txt"), "first\n")
	f.write(filepath.Join(f.repo, "related.txt"), "RELATED_FILE_MARKER\n")
	f.git("add", ".")
	f.git("commit", "-qm", "first")
	f.write(filepath.Join(f.repo, "example.txt"), "first\nsecond\n")
	f.git("add", ".")
	f.git("commit", "-qm", "second")
	f.writeRoster([]string{"plans/"})
	return f
}
func (f *fixture) gitAt(cwd string, args ...string) string {
	f.t.Helper()
	s, e := git(cwd, args...)
	if e != nil {
		f.t.Fatal(e)
	}
	return s
}
func (f *fixture) git(args ...string) string { f.t.Helper(); return f.gitAt(f.repo, args...) }
func (f *fixture) write(path, s string) {
	f.t.Helper()
	if e := os.WriteFile(path, []byte(s), 0600); e != nil {
		f.t.Fatal(e)
	}
}
func (f *fixture) writeObject(path string, v any) {
	f.t.Helper()
	f.write(path, string(jsonBytes(v, true)))
}
func specialist() object {
	return object{"id": "contract-compatibility", "name": "Contract Compatibility", "expertise": "API、型、CLI、設定とconsumerの境界", "mission": "後方互換性と入出力contractの不整合を発見する", "focus": "公開CLIの引数contract", "reason": "公開APIの変更を含むため"}
}
func (f *fixture) writeRoster(excluded []string) {
	f.writeObject(f.roster, object{"reviewers": []any{specialist()}, "adversarial": object{"excluded_context_paths": excluded}})
}
func (f *fixture) run(args ...string) response {
	var out, stderr bytes.Buffer
	code := Run(args, f.repo, &out, &stderr)
	return response{code, out.String(), stderr.String()}
}
func parseObject(t *testing.T, s string) object {
	t.Helper()
	var m object
	if e := json.Unmarshal([]byte(s), &m); e != nil {
		t.Fatalf("invalid JSON %q: %v", s, e)
	}
	return m
}
func (r response) require(t *testing.T, code int) {
	t.Helper()
	if r.code != code {
		t.Fatalf("exit %d, want %d; stdout=%s stderr=%s", r.code, code, r.out, r.stderr)
	}
}
func (r response) errorCode(t *testing.T) string {
	t.Helper()
	return str(obj(parseObject(t, r.stderr)["error"])["code"])
}
func (f *fixture) prepare(args ...string) (string, object) {
	f.t.Helper()
	r := f.run(append([]string{"prepare", "--run-root", f.runs}, args...)...)
	r.require(f.t, 0)
	p := parseObject(f.t, r.out)
	return str(p["run_dir"]), p
}
func (f *fixture) branch() (string, object) { return f.prepare("--mode", "branch", "--base", "HEAD~1") }
func (f *fixture) route(run string) response {
	return f.run("route", "--run-dir", run, "--roster-file", f.roster)
}
func (f *fixture) routed() (string, object) {
	f.t.Helper()
	run, _ := f.branch()
	r := f.route(run)
	r.require(f.t, 0)
	return run, parseObject(f.t, r.out)
}
func promptPath(run, id string) string { return filepath.Join(run, "reviewers", id, "prompt.md") }
func resultPath(run, id string) string { return filepath.Join(run, "reviewers", id, "result.md") }
func read(t *testing.T, path string) string {
	t.Helper()
	b, e := os.ReadFile(path)
	if e != nil {
		t.Fatal(e)
	}
	return string(b)
}
func load(t *testing.T, run string) object {
	t.Helper()
	_, m, e := loadRun(run)
	if e != nil {
		t.Fatal(e)
	}
	return m
}
func mustContain(t *testing.T, s string, values ...string) {
	t.Helper()
	for _, v := range values {
		if !strings.Contains(s, v) {
			t.Errorf("output lacks %q: %s", v, s)
		}
	}
}
func mustNotContain(t *testing.T, s string, values ...string) {
	t.Helper()
	for _, v := range values {
		if strings.Contains(s, v) {
			t.Errorf("output contains %q", v)
		}
	}
}
func requireAbsent(t *testing.T, path string) {
	t.Helper()
	if exists(path) {
		t.Fatalf("unexpected artifact: %s", path)
	}
}
func TestValidateOutputAcceptsJapaneseFindingsHeading(t *testing.T) {
	s := "## 指摘\n### [high] 公開契約が壊れる\n- 対象: example.go:1\n- 問題: 呼び出し元が失敗する\n- 根拠: example.go:1\n- 修正案: 互換性を維持する\n"
	if got := ValidateOutput(s); got != "success" {
		t.Fatal(got)
	}
}
func TestValidateOutputAcceptsLegacyEnglishFindingFormat(t *testing.T) {
	s := "## Findings\n### [high] Public contract breaks\n- Target: example.go:1\n- Problem: callers fail\n- Evidence: example.go:1\n- Suggested fix: preserve compatibility\n"
	if got := ValidateOutput(s); got != "success" {
		t.Fatal(got)
	}
}
func TestValidateOutputAcceptsLegacyEnglishFindingWithoutSectionHeading(t *testing.T) {
	s := "### [high] Public contract breaks\n- Target: example.go:1\n- Problem: callers fail\n- Evidence: example.go:1\n- Suggested fix: preserve compatibility\n"
	if got := ValidateOutput(s); got != "success" {
		t.Fatal(got)
	}
}
func TestValidateOutputAcceptsJapaneseNoFindingsMarker(t *testing.T) {
	if got := ValidateOutput("対応が必要な指摘はありません。\n"); got != "success" {
		t.Fatal(got)
	}
}
func TestPrepareBranchResolvesFullIDsWithoutContextArtifacts(t *testing.T) {
	f := newFixture(t)
	run, p := f.branch()
	st, e := os.Stat(run)
	if e != nil {
		t.Fatal(e)
	}
	if st.Mode().Perm() != 0700 {
		t.Fatal(st.Mode())
	}
	for _, k := range []string{"base", "head"} {
		if id := str(obj(p["target"])[k]); len(id) != 40 || !objectID.MatchString(id) {
			t.Fatal(p)
		}
	}
	if !reflect.DeepEqual(p["changed_files"], []any{"example.txt"}) {
		t.Fatal(p)
	}
	requireAbsent(t, filepath.Join(run, "context-builder"))
	for _, k := range []string{"engine", "model"} {
		if _, ok := p[k]; ok {
			t.Fatal(p)
		}
	}
}
func TestPrepareCommitResolvesFullIDAndChangedPaths(t *testing.T) {
	f := newFixture(t)
	_, p := f.prepare("--mode", "commit", "--commit", "HEAD")
	if len(str(obj(p["target"])["commit"])) != 40 || !reflect.DeepEqual(p["changed_files"], []any{"example.txt"}) {
		t.Fatal(p)
	}
}
func TestPrepareAndLoadAcceptSHA256FullObjectIDs(t *testing.T) {
	f := newFixture(t)
	sha := filepath.Join(f.root, "sha256")
	if _, e := git(f.root, "init", "-q", "--object-format=sha256", sha); e != nil {
		t.Skip("installed Git does not support SHA-256 repositories")
	}
	f.gitAt(sha, "config", "user.name", "Review Test")
	f.gitAt(sha, "config", "user.email", "review-test@example.com")
	f.write(filepath.Join(sha, "example.txt"), "sha256\n")
	f.gitAt(sha, "add", ".")
	f.gitAt(sha, "commit", "-qm", "sha256")
	f.repo = sha
	run, p := f.prepare("--mode", "commit")
	if id := str(obj(p["target"])["commit"]); len(id) != 64 || id != str(obj(load(t, run)["target"])["commit"]) {
		t.Fatal(p)
	}
}
func TestRouteCreatesSmallDirectInvestigationPrompts(t *testing.T) {
	f := newFixture(t)
	run, p := f.branch()
	r := f.route(run)
	r.require(t, 0)
	routed := parseObject(t, r.out)
	if !keys(obj(routed["reviewers"]), "contract-compatibility", "adversarial") {
		t.Fatal(routed)
	}
	prompt := read(t, promptPath(run, "contract-compatibility"))
	target := obj(p["target"])
	mustContain(t, prompt, "API、型、CLI、設定とconsumerの境界", "後方互換性と入出力contractの不整合を発見する", "公開CLIの引数contract", "今回の重点は優先事項であり、探索範囲を限定しない", "diff --find-renames "+str(target["base"])+"..."+str(target["head"]), "git -C "+quote(f.repo), "example.txt", "読み取り専用")
	mustNotContain(t, prompt, "+second")
}
func TestRouteKeepsAdversarialBlindToSelectionAndContextPaths(t *testing.T) {
	f := newFixture(t)
	run, _ := f.branch()
	f.writeRoster([]string{"plans/", "docs/design/"})
	f.route(run).require(t, 0)
	prompt := read(t, promptPath(run, "adversarial"))
	mustContain(t, prompt, "plans/", "docs/design/", "調査してはならない", ":(top,literal,exclude)plans")
	mustNotContain(t, prompt, "公開CLIの引数contract", "公開APIの変更を含むため")
}
func TestAdversarialCommandLiterallyExcludesFileDirectoryAndGlobPaths(t *testing.T) {
	f := newFixture(t)
	if e := os.Mkdir(filepath.Join(f.repo, "plans"), 0700); e != nil {
		t.Fatal(e)
	}
	for path, value := range map[string]string{"plans/secret.md": "DIRECTORY_SECRET", "literal[1].md": "GLOB_SECRET", "line\nbreak.md": "CONTROL_SECRET", "visible.md": "VISIBLE"} {
		f.write(filepath.Join(f.repo, path), value+"\n")
	}
	f.git("add", ".")
	f.git("commit", "-qm", "context paths")
	run, _ := f.branch()
	f.writeRoster([]string{"plans", "literal[1].md", "line\nbreak.md"})
	f.route(run).require(t, 0)
	prompt := read(t, promptPath(run, "adversarial"))
	command := strings.SplitN(strings.SplitN(prompt, "```sh\n", 2)[1], "\n```", 2)[0]
	output, e := exec.Command("sh", "-c", command).CombinedOutput()
	if e != nil {
		t.Fatalf("%v: %s", e, output)
	}
	mustContain(t, string(output), "VISIBLE")
	mustNotContain(t, string(output), "DIRECTORY_SECRET", "GLOB_SECRET", "CONTROL_SECRET")
	inventory := strings.SplitN(strings.SplitN(prompt, "変更パス：\n```json\n", 2)[1], "\n```", 2)[0]
	mustNotContain(t, inventory, "plans", "literal[1].md", `line\nbreak.md`)
}
func TestRouteRejectsLegacyArrayRoster(t *testing.T) {
	f := newFixture(t)
	run, _ := f.branch()
	f.write(f.roster, "[]\n")
	r := f.route(run)
	if r.errorCode(t) != "reviewer_roster_invalid" {
		t.Fatal(r)
	}
	requireAbsent(t, filepath.Join(run, "reviewers"))
}
func TestRouteRejectsUnsafeExcludedContextPaths(t *testing.T) {
	for _, path := range []string{"/tmp/plans", "../plans", "docs/../plans"} {
		t.Run(path, func(t *testing.T) {
			f := newFixture(t)
			run, _ := f.branch()
			f.writeRoster([]string{path})
			r := f.route(run)
			if r.errorCode(t) != "reviewer_roster_invalid" {
				t.Fatal(r)
			}
			requireAbsent(t, filepath.Join(run, "reviewers"))
		})
	}
}
func TestRouteRejectsOversizedPromptBeforePublication(t *testing.T) {
	f := newFixture(t)
	run, _ := f.branch()
	e := routeWithLimit(run, load(t, run), f.roster, io.Discard, 10)
	var protocol *protocolError
	if !errors.As(e, &protocol) || protocol.code != "run_protocol_invalid" {
		t.Fatal(e)
	}
	requireAbsent(t, filepath.Join(run, "reviewers"))
}
func TestRouteRejectsPromptEqualToSizeLimit(t *testing.T) {
	f := newFixture(t)
	run, _ := f.branch()
	m := load(t, run)
	prompt, e := buildPrompt(specialist(), m, resultPath(run, "contract-compatibility"), []string{})
	if e != nil {
		t.Fatal(e)
	}
	e = routeWithLimit(run, m, f.roster, io.Discard, len(prompt))
	if e == nil {
		t.Fatal("size boundary accepted")
	}
	requireAbsent(t, filepath.Join(run, "reviewers"))
}
func TestLocalPromptUsesFixedHeadAndSafeUntrackedContract(t *testing.T) {
	f := newFixture(t)
	f.write(filepath.Join(f.repo, "new.txt"), "new\n")
	run, p := f.prepare("--mode", "local")
	f.route(run).require(t, 0)
	for _, id := range []string{"contract-compatibility", "adversarial"} {
		prompt := read(t, promptPath(run, id))
		mustContain(t, prompt, "diff --find-renames "+str(obj(p["target"])["head"]), "diff --cached --find-renames "+str(obj(p["target"])["head"]), "未追跡のシンボリックリンク", "lstat", "readlink", "参照先をたどったり")
	}
}
func TestManifestTargetRejectsShellInjectionBeforePromptRender(t *testing.T) {
	f := newFixture(t)
	run, _ := f.branch()
	m := load(t, run)
	injected := filepath.Join(f.root, "injected")
	obj(m["target"])["head"] = "$(touch " + injected + ")"
	f.writeObject(filepath.Join(run, "manifest.json"), m)
	r := f.route(run)
	r.require(t, 2)
	requireAbsent(t, injected)
}
func TestPromptInventoryEscapesControlCharactersInChangedPaths(t *testing.T) {
	f := newFixture(t)
	run, _ := f.branch()
	m := load(t, run)
	m["changed_files"] = []any{"line\nbreak.txt"}
	prompt, e := buildPrompt(specialist(), m, filepath.Join(run, "result.md"), []string{})
	if e != nil {
		t.Fatal(e)
	}
	mustContain(t, prompt, `line\nbreak.txt`)
	mustNotContain(t, prompt, "line\nbreak.txt")
}
func TestRepositoryDigestChangesWhenUntrackedModeChanges(t *testing.T) {
	f := newFixture(t)
	path := filepath.Join(f.repo, "script.sh")
	f.write(path, "#!/bin/sh\n")
	before, e := repositoryDigest(f.repo)
	if e != nil {
		t.Fatal(e)
	}
	if e = os.Chmod(path, 0755); e != nil {
		t.Fatal(e)
	}
	after, e := repositoryDigest(f.repo)
	if e != nil {
		t.Fatal(e)
	}
	if before == after {
		t.Fatal("mode change did not change digest")
	}
}
func TestRouteRejectsMoreThanTwoDynamicReviewers(t *testing.T) {
	f := newFixture(t)
	run, _ := f.branch()
	roster := []any{}
	for _, id := range []string{"contract-compatibility", "security", "data-integrity"} {
		r := specialist()
		r["id"] = id
		roster = append(roster, r)
	}
	f.writeObject(f.roster, object{"reviewers": roster, "adversarial": object{"excluded_context_paths": []string{}}})
	r := f.route(run)
	if r.errorCode(t) != "reviewer_roster_invalid" {
		t.Fatal(r)
	}
	requireAbsent(t, filepath.Join(run, "reviewers"))
}
func TestRouteRejectsRemovedQuestionField(t *testing.T) {
	f := newFixture(t)
	run, _ := f.branch()
	reviewer := specialist()
	reviewer["question"] = "公開contractを壊す変更があるか"
	f.writeObject(f.roster, object{"reviewers": []any{reviewer}, "adversarial": object{"excluded_context_paths": []string{}}})
	r := f.route(run)
	if r.errorCode(t) != "reviewer_roster_invalid" {
		t.Fatal(r)
	}
	requireAbsent(t, filepath.Join(run, "reviewers"))
}
func TestWorktreeDriftAfterPrepareBlocksReviewerRouting(t *testing.T) {
	f := newFixture(t)
	f.write(filepath.Join(f.repo, "example.txt"), "dirty before prepare\n")
	run, _ := f.branch()
	f.write(filepath.Join(f.repo, "example.txt"), "changed after prepare\n")
	r := f.route(run)
	if r.errorCode(t) != "repository_drift" {
		t.Fatal(r)
	}
	requireAbsent(t, filepath.Join(run, "reviewers"))
}
func TestCollectValidatesReviewerResultsAndReportsPartialFailure(t *testing.T) {
	f := newFixture(t)
	run, _ := f.routed()
	f.write(resultPath(run, "contract-compatibility"), "No actionable findings.\n")
	f.write(resultPath(run, "adversarial"), "")
	r := f.run("collect", "--run-dir", run)
	r.require(t, 0)
	mustContain(t, r.out, "overall_status: partial_failure", "| Adversarial | protocol_failure(empty_output) |")
}
func TestCollectReturnsNonzeroWhenAllReviewerResultsAreInvalid(t *testing.T) {
	f := newFixture(t)
	run, _ := f.routed()
	for _, id := range []string{"contract-compatibility", "adversarial"} {
		f.write(resultPath(run, id), "")
	}
	r := f.run("collect", "--run-dir", run)
	r.require(t, 1)
	mustContain(t, r.out, "overall_status: failed")
}
func TestCollectRejectsRepositoryDriftAfterReviewerRouting(t *testing.T) {
	f := newFixture(t)
	run, _ := f.routed()
	for _, id := range []string{"contract-compatibility", "adversarial"} {
		f.write(resultPath(run, id), "No actionable findings.\n")
	}
	f.write(filepath.Join(f.repo, "example.txt"), "changed during review\n")
	r := f.run("collect", "--run-dir", run)
	if r.errorCode(t) != "repository_drift" {
		t.Fatal(r)
	}
	mustNotContain(t, r.out, "overall_status: success")
}
func TestCollectRejectsRepositoryDriftDuringResultCollection(t *testing.T) {
	f := newFixture(t)
	run, _ := f.routed()
	for _, id := range []string{"contract-compatibility", "adversarial"} {
		f.write(resultPath(run, id), "No actionable findings.\n")
	}
	changed := false
	reader := func(path string, limit int64) (string, error) {
		s, e := readRegular(path, limit)
		if !changed {
			f.write(filepath.Join(f.repo, "example.txt"), "changed during collect\n")
			changed = true
		}
		return s, e
	}
	var out bytes.Buffer
	_, e := collectWithReader(run, load(t, run), &out, reader)
	var protocol *protocolError
	if !errors.As(e, &protocol) || protocol.code != "repository_drift" {
		t.Fatal(e)
	}
	if out.Len() != 0 {
		t.Fatal(out.String())
	}
}
func TestRouteRefusesPreexistingReviewerArtifactRoot(t *testing.T) {
	f := newFixture(t)
	run, _ := f.branch()
	if e := os.Mkdir(filepath.Join(run, "reviewers"), 0700); e != nil {
		t.Fatal(e)
	}
	r := f.route(run)
	if r.errorCode(t) != "run_protocol_invalid" {
		t.Fatal(r)
	}
}
func TestRepeatRouteRejectsModifiedPublishedPrompt(t *testing.T) {
	f := newFixture(t)
	run, _ := f.routed()
	f.write(promptPath(run, "adversarial"), "tampered\n")
	r := f.route(run)
	if r.errorCode(t) != "run_protocol_invalid" {
		t.Fatal(r)
	}
}
func TestCollectRejectsUnexpectedReviewerArtifact(t *testing.T) {
	f := newFixture(t)
	run, _ := f.routed()
	f.write(filepath.Join(run, "reviewers", "unexpected.txt"), "extra\n")
	r := f.run("collect", "--run-dir", run)
	if r.errorCode(t) != "run_protocol_invalid" {
		t.Fatal(r)
	}
}
func TestRouteRecoversCompletePublicationBeforeManifestUpdate(t *testing.T) {
	f := newFixture(t)
	run, _ := f.routed()
	m := load(t, run)
	m["state"] = "prepared"
	f.writeObject(filepath.Join(run, "manifest.json"), m)
	f.route(run).require(t, 0)
	if load(t, run)["state"] != "routed" {
		t.Fatal("not recovered")
	}
}
func TestRouteRecoveryRejectsRepositoryDrift(t *testing.T) {
	f := newFixture(t)
	run, _ := f.routed()
	m := load(t, run)
	m["state"] = "prepared"
	f.writeObject(filepath.Join(run, "manifest.json"), m)
	f.write(filepath.Join(f.repo, "example.txt"), "drift\n")
	r := f.route(run)
	if r.errorCode(t) != "repository_drift" {
		t.Fatal(r)
	}
}
func TestCleanupRejectsInvalidManifestReviewerID(t *testing.T) {
	f := newFixture(t)
	run, _ := f.routed()
	m := load(t, run)
	obj(arr(m["reviewers"])[0])["id"] = "../outside"
	f.writeObject(filepath.Join(run, "manifest.json"), m)
	r := f.run("cleanup", "--run-dir", run)
	r.require(t, 2)
	if !exists(run) {
		t.Fatal("run removed")
	}
}
func TestPrepareLocalInventoriesStagedUnstagedAndUntrackedPaths(t *testing.T) {
	f := newFixture(t)
	f.write(filepath.Join(f.repo, "example.txt"), "staged\n")
	f.git("add", "example.txt")
	f.write(filepath.Join(f.repo, "example.txt"), "unstaged\n")
	f.write(filepath.Join(f.repo, "new-file.txt"), "untracked marker\n")
	_, p := f.prepare("--mode", "local")
	if !reflect.DeepEqual(p["changed_files"], []any{"example.txt", "new-file.txt"}) {
		t.Fatal(p)
	}
	if _, ok := p["context_prompt_file"]; ok {
		t.Fatal(p)
	}
}
func TestLocalModeDoesNotFollowUntrackedSymbolicLinks(t *testing.T) {
	f := newFixture(t)
	secret := filepath.Join(f.root, "secret.txt")
	f.write(secret, "OUTSIDE_SECRET_MARKER\n")
	if e := os.Symlink(secret, filepath.Join(f.repo, "outside-link")); e != nil {
		t.Fatal(e)
	}
	_, p := f.prepare("--mode", "local")
	mustContain(t, string(jsonBytes(p, false)), "outside-link")
	mustNotContain(t, string(jsonBytes(p, false)), "OUTSIDE_SECRET_MARKER")
}
func TestCleanupRemovesOnlyHelperOwnedRunDirectory(t *testing.T) {
	f := newFixture(t)
	run, _ := f.branch()
	unrelated := filepath.Join(f.root, "unrelated")
	if e := os.Mkdir(unrelated, 0700); e != nil {
		t.Fatal(e)
	}
	f.run("cleanup", "--run-dir", run).require(t, 0)
	requireAbsent(t, run)
	if !exists(unrelated) {
		t.Fatal("unrelated directory removed")
	}
}
func TestCleanupRefusesRunDirectoryWithUnknownContent(t *testing.T) {
	f := newFixture(t)
	run, _ := f.branch()
	unknown := filepath.Join(run, "unknown.txt")
	f.write(unknown, "must survive\n")
	r := f.run("cleanup", "--run-dir", run)
	if r.errorCode(t) != "cleanup_refused" {
		t.Fatal(r)
	}
	mustContain(t, read(t, unknown), "must survive")
}
func TestCleanupRefusesSymlinkedProtocolDirectory(t *testing.T) {
	f := newFixture(t)
	run, _ := f.routed()
	root := filepath.Join(run, "reviewers")
	external := filepath.Join(f.root, "external-reviewers")
	if e := os.Mkdir(external, 0700); e != nil {
		t.Fatal(e)
	}
	f.write(filepath.Join(external, "prompt.md"), "must survive\n")
	if e := os.RemoveAll(root); e != nil {
		t.Fatal(e)
	}
	if e := os.Symlink(external, root); e != nil {
		t.Fatal(e)
	}
	r := f.run("cleanup", "--run-dir", run)
	if r.errorCode(t) != "cleanup_refused" {
		t.Fatal(r)
	}
	mustContain(t, read(t, filepath.Join(external, "prompt.md")), "must survive")
	st, e := os.Lstat(root)
	if e != nil || st.Mode()&os.ModeSymlink == 0 {
		t.Fatal("symlink removed")
	}
}
func TestManifestUpdateFailurePreservesPreviousManifest(t *testing.T) {
	f := newFixture(t)
	run, _ := f.branch()
	path := filepath.Join(run, "manifest.json")
	before := read(t, path)
	e := writeManifestWithRename(run, object{"state": "routed"}, func(string, string) error { return errors.New("interrupted") })
	if e == nil {
		t.Fatal("rename failure ignored")
	}
	if read(t, path) != before {
		t.Fatal("previous manifest changed")
	}
	requireAbsent(t, filepath.Join(run, "manifest.json.pending"))
}
func TestCleanupRejectsSymlinkedRunMetadata(t *testing.T) {
	for _, name := range []string{marker, "manifest.json"} {
		t.Run(name, func(t *testing.T) {
			f := newFixture(t)
			run, _ := f.branch()
			metadata := filepath.Join(run, name)
			external := filepath.Join(f.root, "external")
			f.write(external, read(t, metadata))
			if e := os.Remove(metadata); e != nil {
				t.Fatal(e)
			}
			if e := os.Symlink(external, metadata); e != nil {
				t.Fatal(e)
			}
			f.run("cleanup", "--run-dir", run).require(t, 2)
			if !exists(external) {
				t.Fatal("external file removed")
			}
		})
	}
}
func TestCollectRejectsSymlinkedResultWithoutPrintingItsTarget(t *testing.T) {
	f := newFixture(t)
	run, _ := f.routed()
	secret := filepath.Join(f.root, "secret.txt")
	f.write(secret, "OUTSIDE_SECRET_MARKER\n")
	f.write(resultPath(run, "contract-compatibility"), "No actionable findings.\n")
	if e := os.Symlink(secret, resultPath(run, "adversarial")); e != nil {
		t.Fatal(e)
	}
	r := f.run("collect", "--run-dir", run)
	r.require(t, 0)
	mustContain(t, r.out, "| Adversarial | protocol_failure(invalid_result_file) |")
	mustNotContain(t, r.out, "OUTSIDE_SECRET_MARKER")
}
func TestEngineProcessOptionsAreNotPartOfPublicInterface(t *testing.T) {
	f := newFixture(t)
	r := f.run("--help")
	r.require(t, 0)
	mustNotContain(t, r.out, "--engine", "--model", "--thinking", "--timeout-sec", "reset-context", "validate-context")
}
func TestReviewerPromptsRemainStandaloneTemplates(t *testing.T) {
	files, e := prompts.ReadDir("assets/reviewer-prompts")
	if e != nil {
		t.Fatal(e)
	}
	if len(files) != 2 {
		t.Fatal(files)
	}
	for _, file := range files {
		b, e := prompts.ReadFile("assets/reviewer-prompts/" + file.Name())
		if e != nil {
			t.Fatal(e)
		}
		mustContain(t, string(b), "$investigation_command", "$changed_files_json", "$result_file")
		if !strings.Contains(string(b), "レビュー") {
			t.Fatal("Japanese template missing")
		}
	}
}
func TestCollectRejectsFIFOAndOversizedAndInvalidUTF8Results(t *testing.T) {
	for _, kind := range []string{"fifo", "oversized", "invalid-utf8"} {
		t.Run(kind, func(t *testing.T) {
			f := newFixture(t)
			run, _ := f.routed()
			f.write(resultPath(run, "contract-compatibility"), "No actionable findings.\n")
			path := resultPath(run, "adversarial")
			switch kind {
			case "fifo":
				if e := syscall.Mkfifo(path, 0600); e != nil {
					t.Fatal(e)
				}
			case "oversized":
				f.write(path, strings.Repeat("x", 200001))
			case "invalid-utf8":
				f.write(path, string([]byte{0xff}))
			}
			r := f.run("collect", "--run-dir", run)
			r.require(t, 0)
			mustContain(t, r.out, "protocol_failure(invalid_result_file)")
		})
	}
}

func TestLoadRejectsRunDirectorySymlinkWithTrailingSlash(t *testing.T) {
	f := newFixture(t)
	run, _ := f.branch()
	link := filepath.Join(f.root, "run-link")
	if err := os.Symlink(run, link); err != nil {
		t.Fatal(err)
	}
	result := f.run("cleanup", "--run-dir", link+"/")
	result.require(t, 2)
	if !exists(run) {
		t.Fatal("symlink target was removed")
	}
}

func TestManifestUpdateRejectsPendingSymlinkWithoutTouchingItsTarget(t *testing.T) {
	f := newFixture(t)
	run, _ := f.branch()
	before := read(t, filepath.Join(run, "manifest.json"))
	external := filepath.Join(f.root, "external")
	f.write(external, "must survive\n")
	if err := os.Symlink(external, filepath.Join(run, "manifest.json.pending")); err != nil {
		t.Fatal(err)
	}
	if err := writeManifest(run, object{"state": "routed"}); err == nil {
		t.Fatal("pending symlink accepted")
	}
	if read(t, external) != "must survive\n" || read(t, filepath.Join(run, "manifest.json")) != before {
		t.Fatal("existing input was changed")
	}
}

func TestValidateOutputAcceptsLegacyAndUnicodeLineSeparators(t *testing.T) {
	for _, separator := range []string{"\r\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\u0085", "\u2028", "\u2029"} {
		t.Run(separator, func(t *testing.T) {
			output := strings.Join([]string{"## Findings", "### [high] Contract breaks", "- Target: example.go:1", "- Problem: callers fail", "- Evidence: example.go:1", "- Suggested fix: preserve compatibility"}, separator)
			if status := ValidateOutput(output); status != "success" {
				t.Fatal(status)
			}
		})
	}
}

func TestArgumentErrorsUsePlainUsageAndExitTwo(t *testing.T) {
	for _, args := range [][]string{nil, {"unknown"}, {"prepare", "--unknown"}, {"prepare", "--base"}, {"prepare", "--mode", "unknown"}, {"route"}, {"collect"}, {"cleanup"}} {
		t.Run(strings.Join(args, " "), func(t *testing.T) {
			var out, stderr bytes.Buffer
			code := Run(args, t.TempDir(), &out, &stderr)
			if code != 2 || out.Len() != 0 {
				t.Fatalf("exit %d stdout=%q stderr=%q", code, out.String(), stderr.String())
			}
			mustContain(t, stderr.String(), "usage:", "error:")
			if json.Valid(stderr.Bytes()) {
				t.Fatal("argument errors must remain plain usage text")
			}
		})
	}
}

func TestOperationErrorsRemainJSONAndExitTwo(t *testing.T) {
	var out, stderr bytes.Buffer
	code := Run([]string{"prepare", "--mode", "local"}, t.TempDir(), &out, &stderr)
	if code != 2 || out.Len() != 0 {
		t.Fatalf("exit %d stdout=%q stderr=%q", code, out.String(), stderr.String())
	}
	if got := str(obj(parseObject(t, stderr.String())["error"])["code"]); got != "internal_error" {
		t.Fatal(got)
	}
	mustNotContain(t, stderr.String(), "usage:")
}
