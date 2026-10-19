// Package review fixes Git review targets and validates reviewer artifacts.
package review

import (
	"bytes"
	"crypto/sha256"
	"embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"unicode"
	"unicode/utf16"
	"unicode/utf8"
)

//go:embed assets/reviewer-prompts/*.md
var prompts embed.FS

const marker = ".review-diff-code-run"
const maxPrompt = 1_000_000

var reviewerID = regexp.MustCompile(`^[a-z0-9]+(?:-[a-z0-9]+)*$`)
var digestID = regexp.MustCompile(`^[0-9a-f]{64}$`)
var objectID = regexp.MustCompile(`^[0-9a-f]+$`)
var heading = regexp.MustCompile(`^### \[(critical|high|medium|low)\] .+$`)

type object = map[string]any
type protocolError struct{ code, message string }

func (e *protocolError) Error() string { return e.message }
func fail(code, message string) error  { return &protocolError{code, message} }
func invalid(message string) error     { return errors.New(message) }
func str(v any) string                 { s, _ := v.(string); return s }
func obj(v any) object                 { m, _ := v.(map[string]any); return m }
func arr(v any) []any                  { a, _ := v.([]any); return a }
func keys(m object, names ...string) bool {
	if len(m) != len(names) {
		return false
	}
	for _, n := range names {
		if _, ok := m[n]; !ok {
			return false
		}
	}
	return true
}
func stringList(v any) ([]string, bool) {
	a, ok := v.([]any)
	if !ok {
		return nil, false
	}
	r := make([]string, 0, len(a))
	for _, v := range a {
		s, ok := v.(string)
		if !ok {
			return nil, false
		}
		r = append(r, s)
	}
	return r, true
}
func stringsAny(s []string) []any {
	r := make([]any, 0, len(s))
	for _, v := range s {
		r = append(r, v)
	}
	return r
}
func unique(s []string) bool {
	seen := map[string]bool{}
	for _, v := range s {
		if v == "" || seen[v] {
			return false
		}
		seen[v] = true
	}
	return true
}
func jsonBytes(v any, indent bool) []byte {
	var b bytes.Buffer
	e := json.NewEncoder(&b)
	e.SetEscapeHTML(false)
	if indent {
		e.SetIndent("", "  ")
	}
	_ = e.Encode(v)
	return b.Bytes()
}
func printJSON(w io.Writer, v any) { _, _ = w.Write(jsonBytes(v, false)) }
func command(cwd string, args ...string) (string, error) {
	c := exec.Command(args[0], args[1:]...)
	c.Dir = cwd
	var out, errout bytes.Buffer
	c.Stdout = &out
	c.Stderr = &errout
	err := c.Run()
	if err != nil {
		m := strings.TrimSpace(errout.String())
		if m == "" {
			m = fmt.Sprintf("command failed: %s", strings.Join(args, " "))
		}
		return "", invalid(m)
	}
	return out.String(), nil
}
func git(repo string, args ...string) (string, error) {
	return command(repo, append([]string{"git"}, args...)...)
}
func canonical(p string) (string, error) {
	a, e := filepath.Abs(p)
	if e != nil {
		return "", e
	}
	return filepath.EvalSymlinks(a)
}
func paths(repo string, args ...string) ([]string, error) {
	s, e := git(repo, args...)
	if e != nil {
		return nil, e
	}
	r := []string{}
	for _, p := range strings.Split(s, "\x00") {
		if p != "" {
			r = append(r, p)
		}
	}
	return r, nil
}
func untracked(repo string) ([]string, error) {
	return paths(repo, "ls-files", "--others", "--exclude-standard", "-z")
}
func resolveID(repo, ref string) (string, error) {
	s, e := git(repo, "rev-parse", "--verify", ref+"^{commit}")
	return strings.TrimSpace(s), e
}
func changed(repo, mode string, target object) ([]string, error) {
	switch mode {
	case "branch":
		return paths(repo, "diff", "--find-renames", "--name-only", "-z", str(target["base"])+"..."+str(target["head"]))
	case "commit":
		return paths(repo, "show", "--format=", "--find-renames", "--name-only", "-z", str(target["commit"]))
	}
	all := map[string]bool{}
	for _, args := range [][]string{{"diff", "--name-only", "-z"}, {"diff", "--cached", "--name-only", "-z"}, {"ls-files", "--others", "--exclude-standard", "-z"}} {
		p, e := paths(repo, args...)
		if e != nil {
			return nil, e
		}
		for _, v := range p {
			all[v] = true
		}
	}
	r := make([]string, 0, len(all))
	for p := range all {
		r = append(r, p)
	}
	sort.Strings(r)
	return r, nil
}
func textDigest(b []byte) string { d := sha256.Sum256(b); return hex.EncodeToString(d[:]) }
func repositoryDigest(repo string) (string, error) {
	h := sha256.New()
	for _, args := range [][]string{{"rev-parse", "HEAD"}, {"diff", "--binary", "--no-ext-diff"}, {"diff", "--cached", "--binary", "--no-ext-diff"}} {
		s, e := git(repo, args...)
		if e != nil {
			return "", e
		}
		// Python subprocess text mode normalized CRLF and CR in tracked diffs.
		// Keep persisted state digests compatible across the migration.
		s = strings.NewReplacer("\r\n", "\n", "\r", "\n").Replace(s)
		h.Write([]byte(s))
		h.Write([]byte{0})
	}
	p, e := untracked(repo)
	if e != nil {
		return "", e
	}
	sort.Strings(p)
	for _, relative := range p {
		path := filepath.Join(repo, relative)
		st, e := os.Lstat(path)
		if e != nil {
			return "", e
		}
		metadata := st.Sys().(*syscall.Stat_t)
		for _, part := range []string{relative, strconv.FormatUint(uint64(metadata.Mode&syscall.S_IFMT), 10), strconv.FormatUint(uint64(metadata.Mode&07777), 10)} {
			h.Write([]byte(part))
			h.Write([]byte{0})
		}
		switch {
		case st.Mode()&os.ModeSymlink != 0:
			dest, e := os.Readlink(path)
			if e != nil {
				return "", e
			}
			h.Write([]byte("symlink\x00" + dest))
		case st.Mode().IsRegular():
			h.Write([]byte("file\x00"))
			f, e := os.Open(path)
			if e != nil {
				return "", e
			}
			_, e = io.Copy(h, f)
			f.Close()
			if e != nil {
				return "", e
			}
		default:
			h.Write([]byte("other\x00"))
		}
		h.Write([]byte{0})
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
func readRegular(path string, limit int64) (string, error) {
	fd, e := syscall.Open(path, syscall.O_RDONLY|syscall.O_NONBLOCK|syscall.O_NOFOLLOW, 0)
	if e != nil {
		return "", e
	}
	f := os.NewFile(uintptr(fd), path)
	defer f.Close()
	st, e := f.Stat()
	if e != nil {
		return "", e
	}
	if !st.Mode().IsRegular() || st.Size() > limit {
		return "", invalid("artifact is not a bounded regular file")
	}
	b, e := io.ReadAll(io.LimitReader(f, limit+1))
	if e != nil {
		return "", e
	}
	if int64(len(b)) > limit || !utf8.Valid(b) {
		return "", invalid("artifact exceeds its size limit or is not UTF-8")
	}
	return string(b), nil
}
func writeManifest(run string, m object) error {
	return writeManifestWithRename(run, m, os.Rename)
}

func writeManifestWithRename(run string, m object, rename func(string, string) error) error {
	pending := filepath.Join(run, "manifest.json.pending")
	fd, e := syscall.Open(pending, syscall.O_WRONLY|syscall.O_CREAT|syscall.O_TRUNC|syscall.O_NOFOLLOW, 0600)
	if e != nil {
		return e
	}
	f := os.NewFile(uintptr(fd), pending)
	defer f.Close()
	success := false
	defer func() {
		if !success {
			if st, e := os.Lstat(pending); e == nil && st.Mode().IsRegular() {
				_ = os.Remove(pending)
			}
		}
	}()
	if _, e = f.Write(jsonBytes(m, true)); e != nil {
		return e
	}
	if e = f.Sync(); e != nil {
		return e
	}
	if e = rename(pending, filepath.Join(run, "manifest.json")); e != nil {
		return e
	}
	success = true
	return nil
}
func safeRelative(s string) bool {
	if s == "" || filepath.IsAbs(s) {
		return false
	}
	for _, p := range strings.Split(s, "/") {
		if p == ".." {
			return false
		}
	}
	return true
}
func validReviewers(v any) bool {
	a, ok := v.([]any)
	if !ok || len(a) == 0 {
		return false
	}
	ids := map[string]bool{}
	blind := 0
	for _, v := range a {
		r := obj(v)
		id := str(r["id"])
		fields := []string{"id", "name", "expertise", "mission", "focus", "reason"}
		if id == "adversarial" {
			fields = []string{"id", "name"}
			blind++
		}
		if !keys(r, fields...) || !reviewerID.MatchString(id) || ids[id] {
			return false
		}
		for _, v := range r {
			if str(v) == "" {
				return false
			}
		}
		ids[id] = true
	}
	return blind == 1
}
func validateManifest(m object, run string) error {
	common := []string{"version", "run_dir", "repo", "mode", "target", "changed_files", "repository_state_digest", "state"}
	for _, k := range common {
		if _, ok := m[k]; !ok {
			return invalid("run manifest schema is invalid")
		}
	}
	mode := str(m["mode"])
	state := str(m["state"])
	files, ok := stringList(m["changed_files"])
	if m["version"] != float64(1) || str(m["run_dir"]) != run || !filepath.IsAbs(str(m["repo"])) || (mode != "branch" && mode != "commit" && mode != "local") || !ok || !unique(files) || !digestID.MatchString(str(m["repository_state_digest"])) || (state != "prepared" && state != "routed") {
		return invalid("run manifest schema is invalid")
	}
	format, e := git(str(m["repo"]), "rev-parse", "--show-object-format")
	if e != nil {
		return invalid("run manifest repository object format is invalid")
	}
	length := map[string]int{"sha1": 40, "sha256": 64}[strings.TrimSpace(format)]
	target := obj(m["target"])
	names := []string{"head"}
	if mode == "branch" {
		names = []string{"base", "head"}
	}
	if mode == "commit" {
		names = []string{"commit"}
	}
	if length == 0 || !keys(target, names...) {
		return invalid("run manifest target is invalid")
	}
	for _, v := range target {
		s := str(v)
		if len(s) != length || !objectID.MatchString(s) {
			return invalid("run manifest target is invalid")
		}
	}
	if len(m) > len(common) {
		if len(m) != len(common)+2 {
			return invalid("run manifest schema is invalid")
		}
		rc := obj(m["route_config"])
		excluded, ok := stringList(rc["excluded_context_paths"])
		if !keys(rc, "reviewers", "excluded_context_paths") || !reflect.DeepEqual(rc["reviewers"], m["reviewers"]) || !ok {
			return invalid("run manifest route config is invalid")
		}
		for _, p := range excluded {
			if !safeRelative(p) {
				return invalid("run manifest route config is invalid")
			}
		}
		if !validReviewers(m["reviewers"]) {
			return invalid("run manifest reviewer roster is invalid")
		}
	} else if state == "routed" {
		return invalid("routed manifest is missing route config")
	}
	return nil
}
func loadRun(path string) (string, object, error) {
	path = filepath.Clean(path)
	if st, e := os.Lstat(path); e != nil {
		return "", nil, e
	} else if st.Mode()&os.ModeSymlink != 0 {
		return "", nil, invalid("run directory must not be a symbolic link")
	}
	run, e := canonical(path)
	if e != nil {
		return "", nil, e
	}
	mark, e := readRegular(filepath.Join(run, marker), 100)
	if e != nil {
		return "", nil, invalid("run metadata is missing or invalid")
	}
	if mark != "review-diff-code\n" {
		return "", nil, invalid("run directory is not owned by review-diff-code")
	}
	s, e := readRegular(filepath.Join(run, "manifest.json"), 100000)
	if e != nil {
		return "", nil, invalid("run metadata is missing or invalid")
	}
	var m object
	if e = json.Unmarshal([]byte(s), &m); e != nil {
		return "", nil, invalid("run manifest is missing or invalid")
	}
	if e = validateManifest(m, run); e != nil {
		return "", nil, e
	}
	return run, m, nil
}
func readRoster(path string) (object, error) {
	bad := func(message string) (object, error) { return nil, fail("reviewer_roster_invalid", message) }
	p, e := canonical(path)
	if e != nil {
		return bad("reviewer roster is not valid JSON")
	}
	s, e := readRegular(p, 100000)
	if e != nil {
		return bad("reviewer roster is not valid JSON")
	}
	var rc object
	if e = json.Unmarshal([]byte(s), &rc); e != nil {
		return bad("reviewer roster is not valid JSON")
	}
	roster, ok := rc["reviewers"].([]any)
	blind := obj(rc["adversarial"])
	if !keys(rc, "reviewers", "adversarial") || !ok || len(roster) < 1 || len(roster) > 2 || !keys(blind, "excluded_context_paths") {
		return bad("reviewer roster must use the object schema with one or two dynamic reviewers")
	}
	validated := []any{}
	seen := map[string]bool{}
	for _, v := range roster {
		r := obj(v)
		if !keys(r, "id", "name", "expertise", "mission", "focus", "reason") || !reviewerID.MatchString(str(r["id"])) || str(r["id"]) == "adversarial" {
			return bad("reviewer roster entry is invalid")
		}
		out := object{}
		for k, v := range r {
			s, ok := v.(string)
			if !ok || strings.TrimSpace(s) == "" {
				return bad("reviewer roster entry is invalid")
			}
			out[k] = strings.TrimSpace(s)
		}
		id := str(out["id"])
		if seen[id] {
			return bad("reviewer ids must be unique")
		}
		seen[id] = true
		validated = append(validated, out)
	}
	excluded, ok := stringList(blind["excluded_context_paths"])
	if !ok {
		return bad("excluded context paths must be an array")
	}
	for i, p := range excluded {
		if strings.TrimSpace(p) == "" || !safeRelative(p) {
			return bad("excluded context paths must be repository-relative paths without '..'")
		}
		excluded[i] = strings.TrimSpace(p)
	}
	validated = append(validated, object{"id": "adversarial", "name": "Adversarial"})
	return object{"reviewers": validated, "excluded_context_paths": stringsAny(excluded)}, nil
}
func quote(s string) string {
	if s != "" && regexp.MustCompile(`^[a-zA-Z0-9_@%+=:,./-]+$`).MatchString(s) {
		return s
	}
	return "'" + strings.ReplaceAll(s, "'", "'\"'\"'") + "'"
}
func asciiJSON(v any) string {
	s := strings.TrimSuffix(string(jsonBytes(v, true)), "\n")
	var b strings.Builder
	for _, r := range s {
		if r < 128 {
			b.WriteRune(r)
		} else if r <= 0xffff {
			fmt.Fprintf(&b, `\u%04x`, r)
		} else {
			a, c := utf16.EncodeRune(r)
			fmt.Fprintf(&b, `\u%04x\u%04x`, a, c)
		}
	}
	return b.String()
}
func buildPrompt(r, m object, result string, excluded []string) (string, error) {
	name := "reviewer"
	if str(r["id"]) == "adversarial" {
		name = "adversarial"
	}
	b, e := prompts.ReadFile("assets/reviewer-prompts/" + name + ".md")
	if e != nil {
		return "", e
	}
	repo := quote(str(m["repo"]))
	target := obj(m["target"])
	pathspec := " -- ."
	for _, p := range excluded {
		pathspec += " " + quote(":(top,literal,exclude)"+strings.TrimRight(p, "/"))
	}
	var investigation string
	switch str(m["mode"]) {
	case "branch":
		investigation = "git -C " + repo + " diff --find-renames " + str(target["base"]) + "..." + str(target["head"]) + pathspec
	case "commit":
		investigation = "git -C " + repo + " show --find-renames " + str(target["commit"]) + pathspec
	default:
		investigation = "git -C " + repo + " diff --find-renames " + str(target["head"]) + pathspec + "; git -C " + repo + " diff --cached --find-renames " + str(target["head"]) + pathspec + "; git -C " + repo + " ls-files --others --exclude-standard" + pathspec
	}
	files, _ := stringList(m["changed_files"])
	filtered := []string{}
	for _, p := range files {
		omit := false
		for _, x := range excluded {
			x = strings.TrimRight(x, "/")
			if p == x || strings.HasPrefix(p, x+"/") {
				omit = true
			}
		}
		if !omit {
			filtered = append(filtered, p)
		}
	}
	replacements := map[string]string{"reviewer_name": str(r["name"]), "reviewer_expertise": str(r["expertise"]), "reviewer_mission": str(r["mission"]), "review_focus": str(r["focus"]), "selection_reason": str(r["reason"]), "investigation_command": investigation, "changed_files_json": asciiJSON(filtered), "result_file": result, "excluded_context_paths_json": asciiJSON(excluded)}
	s := string(b)
	pattern := regexp.MustCompile(`\$([a-z_]+)`)
	s = pattern.ReplaceAllStringFunc(s, func(key string) string { return replacements[key[1:]] })
	return strings.TrimRight(s, " \t\r\n") + "\n", nil
}
func validateState(m object) error {
	repo := str(m["repo"])
	files, e := changed(repo, str(m["mode"]), obj(m["target"]))
	if e != nil {
		return e
	}
	d, e := repositoryDigest(repo)
	if e != nil {
		return e
	}
	original, _ := stringList(m["changed_files"])
	if !reflect.DeepEqual(files, original) || d != str(m["repository_state_digest"]) {
		return fail("repository_drift", "repository changed after prepare; discard this run and prepare again")
	}
	return nil
}
func dirEntries(path string) (map[string]bool, error) {
	list, e := os.ReadDir(path)
	if e != nil {
		return nil, e
	}
	m := map[string]bool{}
	for _, v := range list {
		m[v.Name()] = true
	}
	return m, nil
}
func realDir(path string) bool { st, e := os.Lstat(path); return e == nil && st.IsDir() }
func exists(path string) bool  { _, e := os.Lstat(path); return e == nil }
func validateArtifacts(run string, m object) error {
	bad := func(s string) error { return fail("run_protocol_invalid", s) }
	reviewers := arr(m["reviewers"])
	if reviewers == nil {
		return bad("reviewer roster is missing")
	}
	root := filepath.Join(run, "reviewers")
	if !realDir(root) {
		return bad("reviewer artifact root is invalid")
	}
	members, e := dirEntries(root)
	if e != nil {
		return e
	}
	if len(members) != len(reviewers)+1 || !members["integrity.json"] {
		return bad("reviewer artifact root has invalid members")
	}
	for _, v := range reviewers {
		if !members[str(obj(v)["id"])] {
			return bad("reviewer artifact root has invalid members")
		}
	}
	raw, e := readRegular(filepath.Join(root, "integrity.json"), 20000)
	if e != nil {
		return bad("reviewer integrity record is invalid")
	}
	var integrity object
	if e = json.Unmarshal([]byte(raw), &integrity); e != nil {
		return bad("reviewer integrity record is invalid")
	}
	digests := obj(integrity["prompt_digests"])
	if !keys(integrity, "version", "prompt_digests") || integrity["version"] != float64(1) || len(digests) != len(reviewers) {
		return bad("reviewer integrity schema is invalid")
	}
	for _, v := range reviewers {
		id := str(obj(v)["id"])
		if _, ok := digests[id]; !ok {
			return bad("reviewer integrity schema is invalid")
		}
		dir := filepath.Join(root, id)
		if !realDir(dir) {
			return bad("reviewer artifact is incomplete: " + id)
		}
		members, e := dirEntries(dir)
		if e != nil {
			return e
		}
		if !members["prompt.md"] || len(members) > 2 || (len(members) == 2 && !members["result.md"]) {
			return bad("reviewer artifact has invalid members: " + id)
		}
		prompt, e := readRegular(filepath.Join(dir, "prompt.md"), maxPrompt)
		if e != nil || len(prompt) >= maxPrompt {
			return bad("reviewer prompt is invalid: " + id)
		}
		if textDigest([]byte(prompt)) != str(digests[id]) {
			return bad("reviewer prompt digest mismatch: " + id)
		}
	}
	return nil
}
func prepare(cwd string, flags map[string]string, w io.Writer) error {
	raw, e := git(cwd, "rev-parse", "--show-toplevel")
	if e != nil {
		return e
	}
	repo, e := canonical(strings.TrimSpace(raw))
	if e != nil {
		return e
	}
	mode := flags["mode"]
	if mode == "auto" {
		s, e := git(repo, "status", "--porcelain")
		if e != nil {
			return e
		}
		mode = "branch"
		if strings.TrimSpace(s) != "" {
			mode = "local"
		}
	}
	target := object{}
	if mode == "branch" {
		base := flags["base"]
		if base == "" {
			base = "origin/main"
			if _, e := exec.LookPath("gh"); e == nil {
				if out, e := command(repo, "gh", "pr", "view", "--json", "baseRefName", "--jq", ".baseRefName"); e == nil && strings.TrimSpace(out) != "" {
					base = "origin/" + strings.TrimSpace(out)
				}
			}
		}
		id, e := resolveID(repo, base)
		if e != nil {
			return e
		}
		target["base"] = id
	}
	ref := "HEAD"
	key := "head"
	if mode == "commit" {
		ref = flags["commit"]
		key = "commit"
	}
	id, e := resolveID(repo, ref)
	if e != nil {
		return e
	}
	target[key] = id
	files, e := changed(repo, mode, target)
	if e != nil {
		return e
	}
	root := flags["run-root"]
	if root == "" {
		root = os.TempDir()
	}
	if !filepath.IsAbs(root) {
		root = filepath.Join(cwd, root)
	}
	if e = os.MkdirAll(root, 0755); e != nil {
		return e
	}
	run, e := os.MkdirTemp(root, "review-diff-code-")
	if e != nil {
		return e
	}
	run, e = canonical(run)
	if e != nil {
		return e
	}
	if e = os.Chmod(run, 0700); e != nil {
		return e
	}
	if e = os.WriteFile(filepath.Join(run, marker), []byte("review-diff-code\n"), 0600); e != nil {
		return e
	}
	digest, e := repositoryDigest(repo)
	if e != nil {
		return e
	}
	m := object{"version": 1, "run_dir": run, "repo": repo, "mode": mode, "target": target, "changed_files": stringsAny(files), "repository_state_digest": digest, "state": "prepared"}
	if e = writeManifest(run, m); e != nil {
		return e
	}
	printJSON(w, object{"run_dir": run, "target": target, "changed_files": files})
	return nil
}
func printRouted(run string, w io.Writer) error {
	_, m, err := loadRun(run)
	if err != nil {
		return err
	}
	r := object{}
	for _, v := range arr(m["reviewers"]) {
		id := str(obj(v)["id"])
		r[id] = object{"prompt_file": filepath.Join(run, "reviewers", id, "prompt.md"), "result_file": filepath.Join(run, "reviewers", id, "result.md")}
	}
	printJSON(w, object{"run_dir": run, "reviewers": r})
	return nil
}
func route(run string, m object, rosterPath string, w io.Writer) error {
	return routeWithLimit(run, m, rosterPath, w, maxPrompt)
}

func routeWithLimit(run string, m object, rosterPath string, w io.Writer, promptLimit int) error {
	rc, e := readRoster(rosterPath)
	if e != nil {
		return e
	}
	root := filepath.Join(run, "reviewers")
	if str(m["state"]) == "routed" {
		if !reflect.DeepEqual(m["route_config"], rc) {
			return fail("run_protocol_invalid", "reviewer roster changed after routing")
		}
		if e = validateState(m); e != nil {
			return e
		}
		if e = validateArtifacts(run, m); e != nil {
			return e
		}
		return printRouted(run, w)
	}
	if m["route_config"] != nil && !reflect.DeepEqual(m["route_config"], rc) {
		return fail("run_protocol_invalid", "reviewer roster changed during routing")
	}
	if m["route_config"] == nil {
		m["route_config"] = rc
		m["reviewers"] = rc["reviewers"]
		if e = writeManifest(run, m); e != nil {
			return e
		}
	}
	if exists(root) {
		if e = validateState(m); e != nil {
			return e
		}
		if e = validateArtifacts(run, m); e != nil {
			return e
		}
		m["state"] = "routed"
		if e = writeManifest(run, m); e != nil {
			return e
		}
		return printRouted(run, w)
	}
	if e = validateState(m); e != nil {
		return e
	}
	staging, e := os.MkdirTemp(run, ".reviewers-")
	if e != nil {
		return e
	}
	defer os.RemoveAll(staging)
	digests := object{}
	excluded, _ := stringList(rc["excluded_context_paths"])
	for _, v := range arr(rc["reviewers"]) {
		r := obj(v)
		id := str(r["id"])
		dir := filepath.Join(staging, id)
		if e = os.Mkdir(dir, 0700); e != nil {
			return e
		}
		omit := []string{}
		if id == "adversarial" {
			omit = excluded
		}
		prompt, e := buildPrompt(r, m, filepath.Join(root, id, "result.md"), omit)
		if e != nil {
			return e
		}
		if len(prompt) >= promptLimit {
			return fail("run_protocol_invalid", "reviewer prompt is invalid: "+id)
		}
		if e = os.WriteFile(filepath.Join(dir, "prompt.md"), []byte(prompt), 0600); e != nil {
			return e
		}
		digests[id] = textDigest([]byte(prompt))
	}
	if e = os.WriteFile(filepath.Join(staging, "integrity.json"), jsonBytes(object{"version": 1, "prompt_digests": digests}, true), 0600); e != nil {
		return e
	}
	if e = validateState(m); e != nil {
		return e
	}
	if e = os.Rename(staging, root); e != nil {
		return e
	}
	m["state"] = "routed"
	if e = writeManifest(run, m); e != nil {
		return e
	}
	return printRouted(run, w)
}

// ValidateOutput validates the review result protocol, including its legacy English form.
func ValidateOutput(output string) string {
	lines := []string{}
	for _, l := range strings.FieldsFunc(output, func(r rune) bool {
		switch r {
		case '\n', '\r', '\v', '\f', '\x1c', '\x1d', '\x1e', '\u0085', '\u2028', '\u2029':
			return true
		}
		return false
	}) {
		if l = strings.TrimSpace(l); l != "" {
			lines = append(lines, l)
		}
	}
	if len(lines) == 0 {
		return "protocol_failure(empty_output)"
	}
	joined := strings.Join(lines, "\n")
	if joined == "対応が必要な指摘はありません。" || joined == "No actionable findings" || joined == "No actionable findings." {
		return "success"
	}
	fields := []string{"- 対象:", "- 問題:", "- 根拠:", "- 修正案:"}
	english := []string{"- Target:", "- Problem:", "- Evidence:", "- Suggested fix:"}
	explicit := false
	if lines[0] == "## 指摘" {
		lines = lines[1:]
		explicit = true
	} else if lines[0] == "## Findings" {
		lines = lines[1:]
		explicit = true
		fields = english
	}
	if len(lines) == 0 || !heading.MatchString(lines[0]) {
		return "protocol_failure(invalid_format)"
	}
	starts := []int{}
	for i, l := range lines {
		if heading.MatchString(l) {
			starts = append(starts, i)
		}
	}
	if !explicit {
		end := len(lines)
		if len(starts) > 1 {
			end = starts[1]
		}
		for _, l := range lines[1:end] {
			if strings.HasPrefix(l, english[0]) {
				fields = english
			}
		}
	}
	starts = append(starts, len(lines))
	for i := 0; i < len(starts)-1; i++ {
		for _, field := range fields {
			found := false
			for _, l := range lines[starts[i]+1 : starts[i+1]] {
				if strings.HasPrefix(l, field) {
					found = true
				}
			}
			if !found {
				return "protocol_failure(invalid_format)"
			}
		}
	}
	return "success"
}
func collect(run string, m object, w io.Writer) (int, error) {
	return collectWithReader(run, m, w, readRegular)
}

func collectWithReader(run string, m object, w io.Writer, readResult func(string, int64) (string, error)) (int, error) {
	if str(m["state"]) != "routed" {
		return 0, invalid("review run has not been routed")
	}
	if e := validateState(m); e != nil {
		return 0, e
	}
	if e := validateArtifacts(run, m); e != nil {
		return 0, e
	}
	type result struct{ title, status, output string }
	results := []result{}
	successes := 0
	for _, v := range arr(m["reviewers"]) {
		r := obj(v)
		out, e := readResult(filepath.Join(run, "reviewers", str(r["id"]), "result.md"), 200000)
		status := "protocol_failure(invalid_result_file)"
		if e == nil {
			status = ValidateOutput(out)
		} else {
			out = ""
		}
		if status == "success" {
			successes++
		}
		results = append(results, result{str(r["name"]), status, out})
	}
	if e := validateState(m); e != nil {
		return 0, e
	}
	overall := "success"
	if successes == 0 {
		overall = "failed"
	} else if successes < len(results) {
		overall = "partial_failure"
	}
	fmt.Fprintf(w, "# Review Summary\n\noverall_status: %s\nmode: %s\norchestrator: codex_subagents\nreviewer_isolation: context_level\n\n| Reviewer | Status |\n| --- | --- |\n", overall, str(m["mode"]))
	for _, r := range results {
		fmt.Fprintf(w, "| %s | %s |\n", r.title, r.status)
	}
	fmt.Fprintln(w, "\n# レビュー担当別の指摘")
	for _, r := range results {
		out := strings.TrimRightFunc(r.output, unicode.IsSpace)
		if strings.TrimSpace(out) == "" {
			out = "No output."
		}
		fmt.Fprintf(w, "\n## %s\n\nstatus: %s\n\n%s\n", r.title, r.status, out)
	}
	if successes == 0 {
		return 1, nil
	}
	return 0, nil
}
func cleanup(run string, m object) error {
	files := map[string]bool{marker: true, "manifest.json": true, "manifest.json.pending": true, "reviewers/integrity.json": true}
	dirs := map[string]bool{"reviewers": true}
	for _, v := range arr(m["reviewers"]) {
		id := str(obj(v)["id"])
		dirs["reviewers/"+id] = true
		files["reviewers/"+id+"/prompt.md"] = true
		files["reviewers/"+id+"/result.md"] = true
	}
	for d := range dirs {
		p := filepath.Join(run, d)
		if exists(p) && !realDir(p) {
			return fail("cleanup_refused", "protocol directory is not a real directory: "+d)
		}
	}
	unknown := []string{}
	e := filepath.WalkDir(run, func(path string, d os.DirEntry, e error) error {
		if e != nil {
			return e
		}
		if path == run {
			return nil
		}
		rel, e := filepath.Rel(run, path)
		if e != nil {
			return e
		}
		if !files[rel] && !dirs[rel] {
			unknown = append(unknown, rel)
		}
		return nil
	})
	if e != nil {
		return e
	}
	if len(unknown) > 0 {
		sort.Strings(unknown)
		return fail("cleanup_refused", "run directory contains unknown content: "+strings.Join(unknown, ", "))
	}
	ordered := []string{}
	for f := range files {
		ordered = append(ordered, f)
	}
	sort.Sort(sort.Reverse(sort.StringSlice(ordered)))
	for _, f := range ordered {
		if e = os.Remove(filepath.Join(run, f)); e != nil && !os.IsNotExist(e) {
			return e
		}
	}
	ordered = nil
	for d := range dirs {
		ordered = append(ordered, d)
	}
	sort.Sort(sort.Reverse(sort.StringSlice(ordered)))
	for _, d := range ordered {
		if e = os.Remove(filepath.Join(run, d)); e != nil && !os.IsNotExist(e) {
			return e
		}
	}
	return os.Remove(run)
}

// Run executes the CLI without changing the process working directory.
func Run(args []string, cwd string, out, errout io.Writer) int {
	help := "Prepare and validate artifacts for a subagent-based diff review.\nCommands: prepare, route, collect, cleanup\nprepare: --mode auto|branch|local|commit --base REF --commit REF --run-root DIR\nroute: --run-dir DIR --roster-file FILE\ncollect, cleanup: --run-dir DIR\n"
	if len(args) == 1 && (args[0] == "--help" || args[0] == "-h") {
		fmt.Fprint(out, help)
		return 0
	}
	usageError := func(message string) int {
		fmt.Fprint(errout, "usage: review-diff-code {prepare,route,collect,cleanup} [options]\n")
		fmt.Fprintf(errout, "review-diff-code: error: %s\n", message)
		return 2
	}
	report := func(e error) int {
		code := "internal_error"
		var p *protocolError
		if errors.As(e, &p) {
			code = p.code
		}
		printJSON(errout, object{"error": object{"code": code, "message": e.Error()}})
		return 2
	}
	if len(args) == 0 {
		return usageError("a command is required")
	}
	cmd := args[0]
	allowed := map[string]bool{}
	switch cmd {
	case "prepare":
		for _, k := range []string{"mode", "base", "commit", "run-root"} {
			allowed[k] = true
		}
	case "route":
		allowed["run-dir"] = true
		allowed["roster-file"] = true
	case "collect", "cleanup":
		allowed["run-dir"] = true
	default:
		return usageError("unknown command: " + cmd)
	}
	flags := map[string]string{"mode": "auto", "commit": "HEAD"}
	for i := 1; i < len(args); i++ {
		if args[i] == "--help" || args[i] == "-h" {
			fmt.Fprint(out, help)
			return 0
		}
		key, value, eq := strings.Cut(strings.TrimPrefix(args[i], "--"), "=")
		if !strings.HasPrefix(args[i], "--") || !allowed[key] {
			return usageError("unrecognized argument: " + args[i])
		}
		if !eq {
			if i+1 >= len(args) {
				return usageError("missing value for --" + key)
			}
			i++
			value = args[i]
		}
		flags[key] = value
	}
	if cmd == "prepare" {
		if mode := flags["mode"]; mode != "auto" && mode != "branch" && mode != "local" && mode != "commit" {
			return usageError("invalid mode")
		}
		if e := prepare(cwd, flags, out); e != nil {
			return report(e)
		}
		return 0
	}
	if flags["run-dir"] == "" || (cmd == "route" && flags["roster-file"] == "") {
		return usageError("required option is missing")
	}
	runArg := flags["run-dir"]
	if !filepath.IsAbs(runArg) {
		runArg = filepath.Join(cwd, runArg)
	}
	run, m, e := loadRun(runArg)
	if e != nil {
		return report(e)
	}
	switch cmd {
	case "route":
		roster := flags["roster-file"]
		if !filepath.IsAbs(roster) {
			roster = filepath.Join(cwd, roster)
		}
		e = route(run, m, roster, out)
	case "cleanup":
		e = cleanup(run, m)
	case "collect":
		var status int
		status, e = collect(run, m, out)
		if e == nil {
			return status
		}
	}
	if e != nil {
		return report(e)
	}
	return 0
}
