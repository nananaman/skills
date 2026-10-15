// check-apm-deployment compares local APM state without fetching or modifying it.
package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"regexp"
	"sort"
	"strings"
	"unicode/utf8"

	"go.yaml.in/yaml/v3"
)

type object = map[string]any
type hashes [2]string
type snapshot map[string]hashes
type inputError string

func (e inputError) Error() string { return string(e) }
func invalid(s string) error       { return inputError(s) }
func kind(err error) string {
	var bad inputError
	var exit *exec.ExitError
	switch {
	case errors.As(err, &bad):
		return "ValueError"
	case errors.Is(err, fs.ErrNotExist):
		return "FileNotFoundError"
	case errors.Is(err, fs.ErrPermission):
		return "PermissionError"
	case errors.As(err, &exit):
		return "CalledProcessError"
	default:
		return "OSError"
	}
}
func hash(b []byte) string { return fmt.Sprintf("sha256:%x", sha256.Sum256(b)) }
func fileHashes(b []byte) hashes {
	canonical := b
	if !bytes.ContainsRune(b, 0) && utf8.Valid(b) {
		canonical = bytes.ReplaceAll(b, []byte("\r\n"), []byte("\n"))
	}
	return hashes{hash(b), hash(canonical)}
}
func git(repo string, args ...string) ([]byte, error) {
	return exec.Command("git", append([]string{"--no-lazy-fetch", "--no-optional-locks", "-C", repo}, args...)...).Output()
}
func resolved(p string) string {
	p, _ = filepath.Abs(p)
	if r, e := filepath.EvalSymlinks(p); e == nil {
		return r
	}
	// Path.resolve also resolves existing parents of a missing leaf.
	if parent := filepath.Dir(p); parent != p {
		return filepath.Join(resolved(parent), filepath.Base(p))
	}
	return p
}
func within(root, p string) (string, bool) {
	r, e := filepath.Rel(root, p)
	return filepath.ToSlash(r), e == nil && r != ".." && !strings.HasPrefix(r, ".."+string(filepath.Separator))
}
func inspect(path string, cache bool) (snapshot, error) {
	info, e := os.Lstat(path)
	if e != nil {
		return nil, e
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return nil, invalid("skill directory symlink is not inspected")
	}
	if !info.IsDir() {
		return nil, invalid("skill directory missing")
	}
	result := snapshot{}
	e = filepath.WalkDir(path, func(p string, d fs.DirEntry, e error) error {
		if e != nil {
			return e
		}
		if p == path {
			return nil
		}
		if d.IsDir() && d.Name() == "__pycache__" {
			return filepath.SkipDir
		}
		if d.Type()&os.ModeSymlink != 0 {
			return invalid("symlink inside skill is not inspected")
		}
		r, _ := filepath.Rel(path, p)
		r = filepath.ToSlash(r)
		if filepath.Ext(p) == ".pyc" || (cache && r == ".apm-pin") {
			return nil
		}
		if d.IsDir() {
			return nil
		}
		info, e := d.Info()
		if e != nil {
			return e
		}
		if !info.Mode().IsRegular() {
			return invalid("non-regular entry is not inspected")
		}
		content, e := os.ReadFile(p)
		if e != nil {
			return e
		}
		result[r] = fileHashes(content)
		return nil
	})
	if e != nil {
		return nil, e
	}
	if _, ok := result["SKILL.md"]; !ok {
		return nil, invalid("SKILL.md missing")
	}
	return result, nil
}
func commitSnapshot(repo, commit, relative string) (snapshot, error) {
	data, e := git(repo, "ls-tree", "-rz", commit, "--", relative)
	if e != nil {
		return nil, e
	}
	result := snapshot{}
	for _, record := range bytes.Split(data, []byte{0}) {
		if len(record) == 0 {
			continue
		}
		fields := bytes.SplitN(record, []byte{'\t'}, 2)
		if len(fields) != 2 {
			return nil, invalid("invalid Git tree")
		}
		meta := strings.Fields(string(fields[0]))
		if len(meta) != 3 || meta[1] != "blob" || meta[0] == "120000" {
			return nil, invalid("non-regular Git entry is not inspected")
		}
		content, e := git(repo, "cat-file", "blob", meta[2])
		if e != nil {
			return nil, e
		}
		result[strings.TrimPrefix(string(fields[1]), relative+"/")] = fileHashes(content)
	}
	if _, ok := result["SKILL.md"]; !ok {
		return nil, invalid("skill missing at target commit")
	}
	return result, nil
}
func diff[A comparable](a, b map[string]A) []string {
	keys := map[string]bool{}
	for k := range a {
		keys[k] = true
	}
	for k := range b {
		keys[k] = true
	}
	out := []string{}
	for k := range keys {
		av, aok := a[k]
		bv, bok := b[k]
		if aok != bok || av != bv {
			out = append(out, k)
		}
	}
	sort.Strings(out)
	return out
}
func loadYAML(path string) (object, error) {
	b, e := os.ReadFile(path)
	if e != nil {
		return nil, e
	}
	var document yaml.Node
	if e = yaml.Unmarshal(b, &document); e != nil {
		return nil, invalid("invalid YAML mapping")
	}
	// APM uses PyYAML's YAML 1.1 boolean spellings. Keep unquoted on/off
	// and yes/no distinct from quoted strings when loading its state.
	legacyYAMLBooleans(&document)
	var value any
	if e = document.Decode(&value); e != nil {
		return nil, invalid("invalid YAML mapping")
	}
	v, ok := value.(map[string]any)
	if !ok {
		return nil, invalid("YAML mapping required")
	}
	return v, nil
}

func legacyYAMLBooleans(node *yaml.Node) {
	if node.Kind == yaml.ScalarNode && node.Tag == "!!str" && node.Style == 0 {
		switch node.Value {
		case "yes", "Yes", "YES", "on", "On", "ON":
			node.Tag, node.Value = "!!bool", "true"
		case "no", "No", "NO", "off", "Off", "OFF":
			node.Tag, node.Value = "!!bool", "false"
		}
	}
	for _, child := range node.Content {
		legacyYAMLBooleans(child)
	}
}
func obj(v any) object {
	m, _ := v.(map[string]any)
	if m == nil {
		return object{}
	}
	return m
}
func str(v any) string { s, _ := v.(string); return s }
func get(m object, k string, fallback any) any {
	v, ok := m[k]
	if ok {
		return v
	}
	return fallback
}
func expand(value, base, home string) string {
	if strings.HasPrefix(value, "~/") {
		return filepath.Join(home, value[2:])
	}
	if filepath.IsAbs(value) {
		return filepath.Clean(value)
	}
	return filepath.Join(base, value)
}
func localRelative(source, repo, common string) string {
	if r, ok := within(repo, source); ok {
		return r
	}
	b, e := git(source, "rev-parse", "--path-format=absolute", "--git-common-dir")
	if e != nil || strings.TrimSpace(string(b)) != common {
		return ""
	}
	b, e = git(source, "rev-parse", "--show-toplevel")
	if e != nil {
		return ""
	}
	r, ok := within(strings.TrimSpace(string(b)), source)
	if !ok {
		return ""
	}
	return r
}

var managedPath = regexp.MustCompile(`^plugin/skills/[a-z0-9-]+$`)
var fullSHA = regexp.MustCompile(`^[0-9a-f]{40}$`)

type options struct {
	scope, root, home, repo, expected, commit string
	json                                      bool
}

func audit(a options) (object, error) {
	const repository = "nananaman/skills"
	repo, home := resolved(a.repo), resolved(a.home)
	scopeRoot := home
	if a.scope == "project" {
		scopeRoot = resolved(a.root)
	}
	stateRoot := scopeRoot
	if a.scope == "global" {
		stateRoot = filepath.Join(home, ".apm")
	}
	manifestPath := filepath.Join(stateRoot, "apm.yml")
	manifest, e := loadYAML(manifestPath)
	if e != nil {
		return nil, e
	}
	lock, e := loadYAML(filepath.Join(stateRoot, "apm.lock.yaml"))
	if e != nil {
		return nil, e
	}
	validVersion := false
	switch version := lock["lockfile_version"].(type) {
	case string:
		validVersion = version == "1"
	case int:
		validVersion = version == 1
	}
	if !validVersion {
		return nil, invalid("unsupported lockfile version")
	}
	md, ok := get(manifest, "dependencies", object{}).(map[string]any)
	if !ok {
		return nil, invalid("manifest dependencies mapping required")
	}
	dependencies, ok := get(md, "apm", []any{}).([]any)
	if !ok {
		return nil, invalid("dependency list required")
	}
	locked, ok := get(lock, "dependencies", []any{}).([]any)
	if !ok {
		return nil, invalid("dependency list required")
	}
	for _, d := range locked {
		if _, ok := d.(map[string]any); !ok {
			return nil, invalid("lock dependency mapping required")
		}
	}
	b, e := git(repo, "rev-parse", "--verify", "--end-of-options", a.commit+"^{commit}")
	if e != nil {
		return nil, e
	}
	commit := strings.TrimSpace(string(b))
	targetValue := get(manifest, "targets", get(manifest, "target", []any{}))
	var targets []any
	if s, ok := targetValue.(string); ok {
		targets = []any{}
		for _, v := range strings.Split(s, ",") {
			targets = append(targets, strings.TrimSpace(v))
		}
	} else {
		targets, ok = targetValue.([]any)
		if !ok {
			return nil, invalid("target list required")
		}
	}
	findings := []object{}
	rows := []object{}
	report := object{"scope": a.scope, "scope_root": scopeRoot, "manifest": manifestPath, "manifest_realpath": resolved(manifestPath), "lock": filepath.Join(stateRoot, "apm.lock.yaml"), "source_repo": repo, "target_commit": commit}
	if a.expected != "" && resolved(a.expected) != resolved(manifestPath) {
		findings = append(findings, object{"code": "manifest-location-mismatch", "expected": resolved(a.expected)})
	}
	b, e = git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
	if e != nil {
		return nil, e
	}
	common := strings.TrimSpace(string(b))
	matched := map[int]bool{}
	names := map[string]bool{}
	for _, dependency := range dependencies {
		pin, relative, source, sourcePath := "", "", "", ""
		matches := []int{}
		if p, ok := obj(dependency)["path"].(string); ok {
			sourcePath = expand(p, stateRoot, home)
			source = resolved(sourcePath)
			relative = localRelative(source, repo, common)
			if relative == "" {
				continue
			}
			for i, d := range locked {
				p, ok := obj(d)["local_path"].(string)
				if ok && resolved(expand(p, stateRoot, home)) == source {
					matches = append(matches, i)
				}
			}
		} else if reference, ok := dependency.(string); ok && strings.HasPrefix(reference, repository+"/") {
			ref, p, found := strings.Cut(reference, "#")
			pin = p
			relative = strings.TrimPrefix(ref, repository+"/")
			if !found || !fullSHA.MatchString(pin) {
				findings = append(findings, object{"code": "unsupported-managed-reference"})
				continue
			}
			source = filepath.Join(stateRoot, "apm_modules", repository, relative)
			sourcePath = source
			for i, d := range locked {
				m := obj(d)
				if m["repo_url"] == repository && m["virtual_path"] == relative {
					matches = append(matches, i)
				}
			}
		} else {
			continue
		}
		if !managedPath.MatchString(relative) {
			findings = append(findings, object{"code": "unsupported-managed-path"})
			continue
		}
		name := filepath.Base(relative)
		rf := []object{}
		targetReports := object{}
		var pinValue any
		if pin != "" {
			pinValue = pin
		}
		row := object{"name": name, "source": sourcePath, "manifest_commit": pinValue, "lock_commit": nil, "targets": targetReports}
		rows = append(rows, row)
		if names[name] {
			rf = append(rf, object{"code": "duplicate-skill-name"})
		}
		names[name] = true
		if pin == "" && source != filepath.Join(repo, relative) {
			rf = append(rf, object{"code": "source-checkout-mismatch"})
		}
		if pin != "" && pin != commit {
			rf = append(rf, object{"code": "manifest-commit-mismatch"})
		}
		if len(matches) != 1 {
			rf = append(rf, object{"code": "lock-entry-missing-or-duplicate"})
		}
		for _, i := range matches {
			matched[i] = true
		}
		entry := object{}
		if len(matches) == 1 {
			entry = obj(locked[matches[0]])
		}
		row["lock_commit"] = entry["resolved_commit"]
		if pin != "" && row["lock_commit"] != pin {
			rf = append(rf, object{"code": "lock-commit-mismatch"})
		}
		expected, err := commitSnapshot(repo, commit, relative)
		if err != nil {
			row["findings"] = append(rf, object{"code": "target-commit-unverified", "reason": kind(err)})
			row["status"] = "unverified"
			continue
		}
		content, err := inspect(sourcePath, pin != "")
		if err != nil {
			rf = append(rf, object{"code": "source-unverified", "reason": kind(err)})
		} else if changes := diff(expected, content); len(changes) > 0 {
			rf = append(rf, object{"code": "source-content-mismatch", "files": changes})
		}
		deployed, ok := get(entry, "deployed_files", []any{}).([]any)
		if !ok {
			return nil, invalid("invalid deployment records")
		}
		for _, p := range deployed {
			if _, ok := p.(string); !ok {
				return nil, invalid("invalid deployment records")
			}
		}
		lockHashes, ok := get(entry, "deployed_file_hashes", object{}).(map[string]any)
		if !ok {
			return nil, invalid("invalid deployment records")
		}
		for _, h := range lockHashes {
			if _, ok := h.(string); !ok {
				return nil, invalid("invalid deployment records")
			}
		}
		for _, target := range []struct{ name, prefix string }{{"agent-skills", ".agents/skills"}, {"claude", ".claude/skills"}} {
			if !contains(targets, target.name) {
				rf = append(rf, object{"code": "target-not-configured", "target": target.name})
			}
			prefix := target.prefix + "/" + name
			if !contains(deployed, prefix) {
				rf = append(rf, object{"code": "lock-target-missing", "target": target.name})
			}
			destination := filepath.Join(scopeRoot, prefix)
			actual, err := inspect(destination, false)
			changes := []string{}
			status := "match"
			if err != nil {
				status = "unverified"
				rf = append(rf, object{"code": "deployment-unverified", "reason": kind(err), "target": target.name})
			} else {
				changes = diff(expected, actual)
				if len(changes) > 0 {
					status = "mismatch"
					rf = append(rf, object{"code": "deployment-content-mismatch", "target": target.name})
				}
			}
			targetReports[target.name] = object{"path": destination, "status": status, "files": changes}
			dirs := map[string]bool{}
			expectedNames := map[string]bool{}
			expectedHashes := map[string]string{}
			for p, h := range expected {
				expectedNames[p] = true
				expectedHashes[p] = h[1]
				for parent := filepath.ToSlash(filepath.Dir(p)); parent != "."; parent = filepath.ToSlash(filepath.Dir(parent)) {
					dirs[parent] = true
				}
			}
			recorded := map[string]bool{}
			for _, p := range deployed {
				s := p.(string)
				if strings.HasPrefix(s, prefix+"/") {
					r := strings.TrimPrefix(s, prefix+"/")
					if !dirs[r] {
						recorded[r] = true
					}
				}
			}
			if changes := diff(expectedNames, recorded); len(changes) > 0 {
				rf = append(rf, object{"code": "lock-files-mismatch", "target": target.name, "files": changes})
			}
			hashes := map[string]string{}
			for p, h := range lockHashes {
				if strings.HasPrefix(p, prefix+"/") {
					hashes[strings.TrimPrefix(p, prefix+"/")] = h.(string)
				}
			}
			if len(hashes) == 0 {
				rf = append(rf, object{"code": "lock-content-unverified", "target": target.name})
			} else if changes := diff(expectedHashes, hashes); len(changes) > 0 {
				rf = append(rf, object{"code": "lock-content-mismatch", "target": target.name, "files": changes})
			}
		}
		row["findings"] = rf
		row["status"] = "match"
		if len(rf) > 0 {
			row["status"] = "mismatch"
		}
	}
	for i, d := range locked {
		entry := obj(d)
		relative := ""
		if p, ok := entry["local_path"].(string); ok {
			relative = localRelative(resolved(expand(p, stateRoot, home)), repo, common)
		}
		if !matched[i] && (entry["repo_url"] == repository || managedPath.MatchString(relative)) {
			findings = append(findings, object{"code": "orphan-lock-entry", "name": get(entry, "name", entry["repo_url"])})
		}
	}
	if len(rows) == 0 {
		findings = append(findings, object{"code": "no-managed-skills"})
	}
	report["findings"] = findings
	report["skills"] = rows
	return report, nil
}
func contains(values []any, v any) bool {
	for _, x := range values {
		if reflect.DeepEqual(x, v) {
			return true
		}
	}
	return false
}
func encode(w io.Writer, v any) {
	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	_ = enc.Encode(v)
}
func run(args []string, out, stderr io.Writer) int {
	cwd, _ := os.Getwd()
	home, _ := os.UserHomeDir()
	a := options{}
	f := flag.NewFlagSet("check-apm-deployment", flag.ContinueOnError)
	f.SetOutput(stderr)
	f.StringVar(&a.scope, "scope", "", "global or project")
	f.StringVar(&a.root, "root", cwd, "project scope root")
	f.StringVar(&a.home, "home", home, "global user home")
	f.StringVar(&a.repo, "source-repo", "", "source Git checkout")
	f.StringVar(&a.expected, "expected-manifest", "", "expected manifest realpath")
	f.StringVar(&a.commit, "commit", "HEAD", "local commit")
	f.BoolVar(&a.json, "json", false, "JSON report")
	if e := f.Parse(args); e != nil {
		if errors.Is(e, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if (a.scope != "global" && a.scope != "project") || a.repo == "" || f.NArg() != 0 {
		fmt.Fprintln(stderr, "--scope global|project and --source-repo are required")
		return 2
	}
	report, e := audit(a)
	if e != nil {
		reason := "manifest / lock / source repo / local commit を読み取れません"
		if kind(e) == "ValueError" {
			reason = e.Error()
		}
		encode(out, object{"error": kind(e), "status": "unverified", "reason": reason})
		return 2
	}
	if a.json {
		encode(out, report)
	} else {
		fmt.Fprintf(out, "scope: %s  manifest: %s\ntarget commit: %s\n", a.scope, report["manifest_realpath"], report["target_commit"])
		for _, row := range report["skills"].([]object) {
			fmt.Fprintf(out, "%s: %s\n", row["name"], row["status"])
			for _, finding := range row["findings"].([]object) {
				fmt.Fprint(out, "  ")
				encode(out, finding)
			}
		}
		for _, finding := range report["findings"].([]object) {
			encode(out, finding)
		}
	}
	if len(report["findings"].([]object)) > 0 {
		return 1
	}
	for _, row := range report["skills"].([]object) {
		if len(row["findings"].([]object)) > 0 {
			return 1
		}
	}
	return 0
}
func main() { os.Exit(run(os.Args[1:], os.Stdout, os.Stderr)) }
