package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"regexp"
	"strings"
	"testing"

	"go.yaml.in/yaml/v3"
)

type fixture struct {
	t                                    *testing.T
	root, repo, skill, home, apm, commit string
	manifest, lock                       object
}

func write(t *testing.T, path string, data []byte) {
	t.Helper()
	if e := os.MkdirAll(filepath.Dir(path), 0755); e != nil {
		t.Fatal(e)
	}
	if e := os.WriteFile(path, data, 0644); e != nil {
		t.Fatal(e)
	}
}
func command(t *testing.T, dir string, args ...string) string {
	t.Helper()
	cmd := exec.Command(args[0], args[1:]...)
	cmd.Dir = dir
	b, e := cmd.CombinedOutput()
	if e != nil {
		t.Fatalf("%v: %v %s", args, e, b)
	}
	return strings.TrimSpace(string(b))
}
func (f *fixture) git(args ...string) string {
	return command(f.t, f.repo, append([]string{"git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false"}, args...)...)
}
func copyTree(t *testing.T, source, dest string) {
	t.Helper()
	e := filepath.WalkDir(source, func(p string, d os.DirEntry, e error) error {
		if e != nil {
			return e
		}
		rel, _ := filepath.Rel(source, p)
		target := filepath.Join(dest, rel)
		if d.IsDir() {
			return os.MkdirAll(target, 0755)
		}
		b, e := os.ReadFile(p)
		if e != nil {
			return e
		}
		return os.WriteFile(target, b, 0644)
	})
	if e != nil {
		t.Fatal(e)
	}
}
func newFixture(t *testing.T) *fixture {
	t.Helper()
	root := resolved(t.TempDir())
	f := &fixture{t: t, root: root, repo: filepath.Join(root, "source"), home: filepath.Join(root, "home")}
	f.skill = filepath.Join(f.repo, "plugin/skills/example")
	f.apm = filepath.Join(f.home, ".apm")
	write(t, filepath.Join(f.skill, "SKILL.md"), []byte("---\nname: example\ndescription: test\n---\nCurrent\n"))
	f.git("init", "-q")
	f.git("config", "user.email", "test@example.invalid")
	f.git("config", "user.name", "Test")
	f.git("config", "core.autocrlf", "false")
	f.git("add", ".")
	f.git("commit", "-qm", "fixture")
	f.commit = f.git("rev-parse", "HEAD")
	f.manifest = object{"target": "claude,agent-skills", "dependencies": object{"apm": []any{object{"path": f.skill}}}}
	deployed := []any{}
	hashes := object{}
	for _, target := range []string{".agents", ".claude"} {
		prefix := target + "/skills/example"
		deployed = append(deployed, prefix, prefix+"/SKILL.md")
		b, _ := os.ReadFile(filepath.Join(f.skill, "SKILL.md"))
		hashes[prefix+"/SKILL.md"] = hash(b)
		copyTree(t, f.skill, filepath.Join(f.home, prefix))
	}
	f.lock = object{"lockfile_version": "1", "dependencies": []any{object{"repo_url": "_local/example", "source": "local", "local_path": f.skill, "package_type": "claude_skill", "deployed_files": deployed, "deployed_file_hashes": hashes}}}
	return f
}
func (f *fixture) entry() object { return f.lock["dependencies"].([]any)[0].(object) }
func (f *fixture) save(base string) {
	f.t.Helper()
	for name, v := range map[string]object{"apm.yml": f.manifest, "apm.lock.yaml": f.lock} {
		b, e := yaml.Marshal(v)
		if e != nil {
			f.t.Fatal(e)
		}
		p := filepath.Join(base, name)
		old, _ := os.ReadFile(p)
		if !bytes.Equal(old, b) {
			write(f.t, p, b)
		}
	}
}
func (f *fixture) audit(args ...string) (int, object) {
	f.t.Helper()
	f.save(f.apm)
	return f.invoke(args...)
}
func (f *fixture) invoke(args ...string) (int, object) {
	f.t.Helper()
	var stdout, stderr bytes.Buffer
	code := run(append([]string{"--scope", "global", "--home", f.home, "--source-repo", f.repo, "--json"}, args...), &stdout, &stderr)
	var report object
	if e := json.Unmarshal(stdout.Bytes(), &report); e != nil {
		f.t.Fatalf("code=%d stderr=%s stdout=%s: %v", code, &stderr, &stdout, e)
	}
	return code, report
}
func rows(r object) []any { return r["skills"].([]any) }
func row(r object) object { return obj(rows(r)[0]) }
func codes(r object) map[string]bool {
	out := map[string]bool{}
	for _, v := range r["findings"].([]any) {
		out[str(obj(v)["code"])] = true
	}
	for _, r := range rows(r) {
		for _, v := range obj(r)["findings"].([]any) {
			out[str(obj(v)["code"])] = true
		}
	}
	return out
}
func expectCode(t *testing.T, code, want int, r object, wantFinding string) {
	t.Helper()
	if code != want {
		t.Fatalf("exit %d want %d: %v", code, want, r)
	}
	if wantFinding != "" && !codes(r)[wantFinding] {
		t.Fatalf("missing %s: %v", wantFinding, r)
	}
}
func status(r object, target string) string {
	return str(obj(obj(row(r)["targets"])[target])["status"])
}
func (f *fixture) pin() {
	f.manifest["dependencies"] = object{"apm": []any{"nananaman/skills/plugin/skills/example#" + f.commit}}
	entry := f.entry()
	delete(entry, "source")
	delete(entry, "local_path")
	entry["repo_url"] = "nananaman/skills"
	entry["virtual_path"] = "plugin/skills/example"
	entry["resolved_commit"] = f.commit
	cache := filepath.Join(f.apm, "apm_modules/nananaman/skills/plugin/skills/example")
	copyTree(f.t, f.skill, cache)
	write(f.t, filepath.Join(cache, ".apm-pin"), []byte(f.commit))
}
func (f *fixture) recommit(content string) {
	write(f.t, filepath.Join(f.skill, "SKILL.md"), []byte(content))
	f.git("add", ".")
	f.git("commit", "-qm", "new version")
}

func TestUnchangedDeploymentsPreserveAllInputBytesAndTimes(t *testing.T) {
	f := newFixture(t)
	f.audit()
	type fileState struct {
		Data     string
		Modified int64
	}
	capture := func() map[string]fileState {
		state := map[string]fileState{}
		e := filepath.WalkDir(f.root, func(p string, d os.DirEntry, e error) error {
			if e != nil {
				return e
			}
			if d.Type().IsRegular() {
				b, e := os.ReadFile(p)
				if e != nil {
					return e
				}
				info, e := d.Info()
				if e != nil {
					return e
				}
				state[p] = fileState{string(b), info.ModTime().UnixNano()}
			}
			return nil
		})
		if e != nil {
			t.Fatal(e)
		}
		return state
	}
	before := capture()
	code, r := f.audit()
	expectCode(t, code, 0, r, "")
	if row(r)["status"] != "match" || r["target_commit"] != f.commit {
		t.Fatal(r)
	}
	if !reflect.DeepEqual(before, capture()) {
		t.Fatal("audit changed an input")
	}
}
func TestOldDeploymentsReportBothTargetsAndStaleLock(t *testing.T) {
	f := newFixture(t)
	f.recommit("New version\n")
	code, r := f.audit()
	expectCode(t, code, 1, r, "lock-content-mismatch")
	if status(r, "claude") != "mismatch" || status(r, "agent-skills") != "mismatch" {
		t.Fatal(r)
	}
}
func TestOnlyStaleSideReportsDeploymentMismatch(t *testing.T) {
	f := newFixture(t)
	write(t, filepath.Join(f.home, ".claude/skills/example/SKILL.md"), []byte("Stale\n"))
	code, r := f.audit()
	expectCode(t, code, 1, r, "")
	if status(r, "agent-skills") != "match" || status(r, "claude") != "mismatch" {
		t.Fatal(r)
	}
}
func TestDifferentWorktreeIsReportedEvenWithIdenticalContents(t *testing.T) {
	f := newFixture(t)
	other := filepath.Join(f.root, "other")
	f.git("worktree", "add", "--detach", "-q", other, "HEAD")
	source := filepath.Join(other, "plugin/skills/example")
	f.manifest["dependencies"] = object{"apm": []any{object{"path": source}}}
	f.entry()["local_path"] = source
	code, r := f.audit()
	expectCode(t, code, 1, r, "source-checkout-mismatch")
	if status(r, "claude") != "match" {
		t.Fatal(r)
	}
}
func TestMissingTargetDoesNotHideMatchingSide(t *testing.T) {
	f := newFixture(t)
	if e := os.RemoveAll(filepath.Join(f.home, ".claude/skills/example")); e != nil {
		t.Fatal(e)
	}
	code, r := f.audit()
	expectCode(t, code, 1, r, "")
	if status(r, "claude") != "unverified" || status(r, "agent-skills") != "match" {
		t.Fatal(r)
	}
}
func TestFullSHAPinChecksLockCacheAndCommit(t *testing.T) {
	f := newFixture(t)
	f.pin()
	code, r := f.audit()
	expectCode(t, code, 0, r, "")
	if row(r)["manifest_commit"] != f.commit || row(r)["lock_commit"] != f.commit {
		t.Fatal(r)
	}
}
func TestStaleLockSHACannotBeHiddenByMatchingBytes(t *testing.T) {
	f := newFixture(t)
	f.pin()
	f.entry()["resolved_commit"] = strings.Repeat("0", 40)
	code, r := f.audit()
	expectCode(t, code, 1, r, "lock-commit-mismatch")
	if status(r, "claude") != "match" {
		t.Fatal(r)
	}
}
func TestOldManifestPinComparedWithRequestedCommit(t *testing.T) {
	f := newFixture(t)
	f.pin()
	f.recommit("New version\n")
	code, r := f.audit()
	expectCode(t, code, 1, r, "manifest-commit-mismatch")
}
func TestProjectScopeDoesNotReadGlobalDeployments(t *testing.T) {
	f := newFixture(t)
	project := filepath.Join(f.root, "project")
	f.manifest["dependencies"] = object{"apm": []any{object{"path": "../source/plugin/skills/example"}}}
	f.entry()["local_path"] = "../source/plugin/skills/example"
	f.save(project)
	for _, target := range []string{".agents", ".claude"} {
		copyTree(t, f.skill, filepath.Join(project, target, "skills/example"))
	}
	write(t, filepath.Join(f.home, ".claude/skills/example/SKILL.md"), []byte("Different global copy\n"))
	code, r := f.audit("--scope", "project", "--root", project)
	expectCode(t, code, 0, r, "")
	if r["scope_root"] != project {
		t.Fatal(r)
	}
}
func TestExpectedManifestMismatch(t *testing.T) {
	f := newFixture(t)
	path := filepath.Join(f.root, "proposed.yml")
	write(t, path, []byte("target: claude\n"))
	code, r := f.audit("--expected-manifest", path)
	expectCode(t, code, 1, r, "manifest-location-mismatch")
}
func TestLockMustRecordTargetInSelectedScope(t *testing.T) {
	f := newFixture(t)
	f.entry()["deployed_files"] = []any{".claude/skills/example"}
	code, r := f.audit()
	expectCode(t, code, 1, r, "lock-target-missing")
}
func TestExtraDeploymentFileDoesNotExposeContents(t *testing.T) {
	f := newFixture(t)
	write(t, filepath.Join(f.home, ".agents/skills/example/unexpected.txt"), []byte("private fixture sentinel"))
	code, r := f.audit()
	expectCode(t, code, 1, r, "deployment-content-mismatch")
	b, _ := json.Marshal(r)
	if bytes.Contains(b, []byte("private fixture sentinel")) || !bytes.Contains(b, []byte("unexpected.txt")) {
		t.Fatal(string(b))
	}
}
func TestShortPinDoesNotUseNetwork(t *testing.T) {
	f := newFixture(t)
	f.manifest["dependencies"] = object{"apm": []any{"nananaman/skills/plugin/skills/example#main"}}
	code, r := f.audit()
	expectCode(t, code, 1, r, "unsupported-managed-reference")
}
func TestMissingFileHashesRemainUnverified(t *testing.T) {
	f := newFixture(t)
	delete(f.entry(), "deployed_file_hashes")
	code, r := f.audit()
	expectCode(t, code, 1, r, "lock-content-unverified")
	if status(r, "claude") != "match" {
		t.Fatal(r)
	}
}
func TestMissingLockEntryIsReportedWithMatchingTargets(t *testing.T) {
	f := newFixture(t)
	f.lock["dependencies"] = []any{}
	code, r := f.audit()
	expectCode(t, code, 1, r, "lock-entry-missing-or-duplicate")
}
func TestUndeclaredManagedLockEntryIsReported(t *testing.T) {
	f := newFixture(t)
	f.lock["dependencies"] = append(f.lock["dependencies"].([]any), object{"repo_url": "nananaman/skills", "virtual_path": "plugin/skills/removed", "name": "removed"})
	code, r := f.audit()
	expectCode(t, code, 1, r, "orphan-lock-entry")
}
func TestLocalEditDistinguishedFromDeploymentDrift(t *testing.T) {
	f := newFixture(t)
	write(t, filepath.Join(f.skill, "SKILL.md"), []byte("Uncommitted\n"))
	code, r := f.audit()
	expectCode(t, code, 1, r, "source-content-mismatch")
	if status(r, "agent-skills") != "match" {
		t.Fatal(r)
	}
}
func TestSymlinkWithinSkillIsNotRead(t *testing.T) {
	f := newFixture(t)
	outside := filepath.Join(f.root, "outside.txt")
	write(t, outside, []byte("private symlink sentinel"))
	if e := os.Symlink(outside, filepath.Join(f.home, ".agents/skills/example/link")); e != nil {
		t.Fatal(e)
	}
	code, r := f.audit()
	expectCode(t, code, 1, r, "deployment-unverified")
	b, _ := json.Marshal(r)
	if bytes.Contains(b, []byte("private symlink sentinel")) {
		t.Fatal(string(b))
	}
}
func TestInvalidInputSchemasReturnExitTwo(t *testing.T) {
	for _, tc := range []struct {
		name   string
		change func(*fixture)
	}{{"lock dependency", func(f *fixture) { f.lock["dependencies"] = []any{"invalid"} }}, {"manifest dependency", func(f *fixture) { f.manifest["dependencies"] = []any{} }}, {"deployment record", func(f *fixture) { f.entry()["deployed_files"] = []any{42} }}, {"target type", func(f *fixture) { f.manifest["target"] = 42 }}, {"lock version", func(f *fixture) { f.lock["lockfile_version"] = 2 }}} {
		t.Run(tc.name, func(t *testing.T) {
			f := newFixture(t)
			tc.change(f)
			code, r := f.audit()
			if code != 2 || r["status"] != "unverified" {
				t.Fatal(code, r)
			}
		})
	}
}
func TestUnavailableLocalCommitReturnsInputError(t *testing.T) {
	f := newFixture(t)
	code, r := f.audit("--commit", strings.Repeat("f", 40))
	if code != 2 || r["status"] != "unverified" {
		t.Fatal(code, r)
	}
}
func TestUnconfiguredTargetCannotFullyMatch(t *testing.T) {
	f := newFixture(t)
	f.manifest["target"] = "claude"
	code, r := f.audit()
	expectCode(t, code, 1, r, "target-not-configured")
}
func TestSkillDirectorySymlinkIsNotFollowed(t *testing.T) {
	f := newFixture(t)
	dest := filepath.Join(f.home, ".agents/skills/example")
	if e := os.RemoveAll(dest); e != nil {
		t.Fatal(e)
	}
	if e := os.Symlink(f.skill, dest); e != nil {
		t.Fatal(e)
	}
	code, r := f.audit()
	expectCode(t, code, 1, r, "deployment-unverified")
	if status(r, "agent-skills") != "unverified" {
		t.Fatal(r)
	}
}
func TestLocalSourceSymlinkIsUnverifiedBeforeReading(t *testing.T) {
	f := newFixture(t)
	alias := filepath.Join(f.root, "alias")
	if e := os.Symlink(f.skill, alias); e != nil {
		t.Fatal(e)
	}
	f.manifest["dependencies"] = object{"apm": []any{object{"path": alias}}}
	f.entry()["local_path"] = alias
	code, r := f.audit()
	expectCode(t, code, 1, r, "source-unverified")
}
func TestOrphanLocalEntryInOtherWorktree(t *testing.T) {
	f := newFixture(t)
	other := filepath.Join(f.root, "other")
	f.git("worktree", "add", "--detach", "-q", other, "HEAD")
	f.lock["dependencies"] = append(f.lock["dependencies"].([]any), object{"repo_url": "_local/example", "local_path": filepath.Join(other, "plugin/skills/example"), "source": "local"})
	code, r := f.audit()
	expectCode(t, code, 1, r, "orphan-lock-entry")
}
func TestCorrectHashDoesNotHideMissingFileRecord(t *testing.T) {
	f := newFixture(t)
	files := f.entry()["deployed_files"].([]any)
	f.entry()["deployed_files"] = []any{files[0], files[2], files[3]}
	code, r := f.audit()
	expectCode(t, code, 1, r, "lock-files-mismatch")
}
func TestLockCRLFNormalizationRetainsExactContentComparison(t *testing.T) {
	f := newFixture(t)
	content := []byte("---\r\nname: example\r\ndescription: test\r\n---\r\n")
	write(t, filepath.Join(f.skill, "SKILL.md"), content)
	f.git("add", ".")
	f.git("commit", "-qm", "CRLF fixture")
	for _, target := range []string{".agents", ".claude"} {
		write(t, filepath.Join(f.home, target, "skills/example/SKILL.md"), content)
		obj(f.entry()["deployed_file_hashes"])[target+"/skills/example/SKILL.md"] = hash(bytes.ReplaceAll(content, []byte("\r\n"), []byte("\n")))
	}
	code, r := f.audit()
	expectCode(t, code, 0, r, "")
}
func TestBinaryAndBareCRLockHashKeepOriginalBytes(t *testing.T) {
	f := newFixture(t)
	for name, content := range map[string][]byte{"nul.bin": []byte("zero\x00\r\n"), "invalid.bin": {255, 13, 10}, "bare.txt": []byte("bare\rreturn")} {
		write(t, filepath.Join(f.skill, name), content)
		for _, target := range []string{".agents", ".claude"} {
			prefix := target + "/skills/example/" + name
			write(t, filepath.Join(f.home, prefix), content)
			f.entry()["deployed_files"] = append(f.entry()["deployed_files"].([]any), prefix)
			obj(f.entry()["deployed_file_hashes"])[prefix] = hash(content)
		}
	}
	f.git("add", ".")
	f.git("commit", "-qm", "binary fixture")
	code, r := f.audit()
	expectCode(t, code, 0, r, "")
}
func TestMissingPartialCloneBlobCannotInvokeRemoteHelper(t *testing.T) {
	f := newFixture(t)
	marker := filepath.Join(f.root, "fetch-invoked")
	helperDir := filepath.Join(f.root, "bin")
	helper := filepath.Join(helperDir, "git-remote-auditprobe")
	write(t, helper, []byte("#!/bin/sh\nprintf invoked > '"+marker+"'\nexit 1\n"))
	if e := os.Chmod(helper, 0755); e != nil {
		t.Fatal(e)
	}
	t.Setenv("PATH", helperDir+string(os.PathListSeparator)+os.Getenv("PATH"))
	f.git("config", "remote.origin.url", "auditprobe::fixture")
	f.git("config", "remote.origin.promisor", "true")
	f.git("config", "extensions.partialClone", "origin")
	oid := f.git("hash-object", "plugin/skills/example/SKILL.md")
	if e := os.Remove(filepath.Join(f.repo, ".git/objects", oid[:2], oid[2:])); e != nil {
		t.Fatal(e)
	}
	code, r := f.audit()
	expectCode(t, code, 1, r, "target-commit-unverified")
	if _, e := os.Stat(marker); !os.IsNotExist(e) {
		t.Fatal("audit invoked remote helper")
	}
}
func TestUnreadableExtraDirectoryIsUnverified(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root bypasses read permissions")
	}
	f := newFixture(t)
	blocked := filepath.Join(f.home, ".agents/skills/example/blocked")
	write(t, filepath.Join(blocked, "extra.txt"), []byte("unreadable"))
	if e := os.Chmod(blocked, 0); e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { _ = os.Chmod(blocked, 0700) })
	code, r := f.audit()
	expectCode(t, code, 1, r, "deployment-unverified")
	if status(r, "agent-skills") != "unverified" {
		t.Fatal(r)
	}
}
func TestDeploymentNewlineDriftDoesNotChangeLockResult(t *testing.T) {
	f := newFixture(t)
	dest := filepath.Join(f.home, ".claude/skills/example/SKILL.md")
	b, _ := os.ReadFile(dest)
	write(t, dest, bytes.ReplaceAll(b, []byte("\n"), []byte("\r\n")))
	code, r := f.audit()
	expectCode(t, code, 1, r, "deployment-content-mismatch")
	if codes(r)["lock-content-mismatch"] {
		t.Fatal(r)
	}
}
func TestCopiedSkillBuildsAndRunsWithoutRepositoryResources(t *testing.T) {
	f := newFixture(t)
	f.save(f.apm)
	source := resolved("../..")
	module := filepath.Join(f.root, "standalone-skill")
	copyTree(t, source, module)
	binary := filepath.Join(f.root, "audit-cli")
	command(t, module, "go", "build", "-mod=readonly", "-o", binary, "./cmd/check-apm-deployment")
	cmd := exec.Command(binary, "--scope", "global", "--home", f.home, "--source-repo", f.repo, "--json")
	cmd.Dir = f.root
	b, e := cmd.CombinedOutput()
	if e != nil {
		t.Fatal(e, string(b))
	}
	var r object
	if e = json.Unmarshal(b, &r); e != nil {
		t.Fatal(e)
	}
	if row(r)["status"] != "match" {
		t.Fatal(r)
	}
}
func TestHelpAndInvalidInvocationExitCodes(t *testing.T) {
	for _, tc := range []struct {
		args []string
		want int
	}{{[]string{"--help"}, 0}, {nil, 2}, {[]string{"--scope", "bogus", "--source-repo", "."}, 2}, {[]string{"--unknown"}, 2}} {
		t.Run(fmt.Sprint(tc.args), func(t *testing.T) {
			var out, err bytes.Buffer
			if got := run(tc.args, &out, &err); got != tc.want {
				t.Fatal(got, tc.want)
			}
		})
	}
}

func TestAPMYAMLBooleanSpellingsPreserveQuotedStrings(t *testing.T) {
	path := filepath.Join(t.TempDir(), "manifest.yml")
	write(t, path, []byte("plain: off\nquoted: 'off'\nexplicit: !!str off\nother: YeS\n"))
	got, err := loadYAML(path)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(got, object{"plain": false, "quoted": "off", "explicit": "off", "other": "YeS"}) {
		t.Fatal(got)
	}
}

func TestFloatingLockVersionIsNotIntegerSchemaVersion(t *testing.T) {
	f := newFixture(t)
	f.save(f.apm)
	path := filepath.Join(f.apm, "apm.lock.yaml")
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	content = regexp.MustCompile(`(?m)^lockfile_version:.*$`).ReplaceAll(content, []byte("lockfile_version: 1.0"))
	write(t, path, content)
	code, report := f.invoke()
	if code != 2 || report["status"] != "unverified" {
		t.Fatal(code, report)
	}
}
