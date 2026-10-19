// Workbench stores local skill experiments and executes the Codex CLI.
package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"html"
	"io"
	"math"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

//go:embed main.go
var adapterSource []byte

type object = map[string]any

func require(ok bool, message string) {
	if !ok {
		panic(fmt.Errorf("%s", message))
	}
}
func must(err error) {
	if err != nil {
		panic(err)
	}
}
func obj(v any) object    { m, ok := v.(map[string]any); require(ok, "expected an object"); return m }
func array(v any) []any   { a, ok := v.([]any); require(ok, "expected a list"); return a }
func text(v any) string   { s, ok := v.(string); require(ok, "expected a string"); return s }
func nonempty(v any) bool { s, ok := v.(string); return ok && strings.TrimSpace(s) != "" }
func oneOf(v any, options ...string) bool {
	s, ok := v.(string)
	if !ok {
		return false
	}
	for _, o := range options {
		if s == o {
			return true
		}
	}
	return false
}
func fields(m object, required []string, optional ...string) {
	allowed := map[string]bool{}
	for _, k := range required {
		_, ok := m[k]
		require(ok, "missing field: "+k)
		allowed[k] = true
	}
	for _, k := range optional {
		allowed[k] = true
	}
	for k := range m {
		require(allowed[k], "invalid field: "+k)
	}
}

var idPattern = regexp.MustCompile(`^[a-zA-Z0-9_-]+$`)

func identifier(v any) string {
	s, ok := v.(string)
	require(ok && idPattern.MatchString(s), "invalid identifier")
	return s
}
func read(path string) any {
	data, err := os.ReadFile(path)
	must(err)
	d := json.NewDecoder(bytes.NewReader(data))
	d.UseNumber()
	var v any
	must(d.Decode(&v))
	var extra any
	require(d.Decode(&extra) == io.EOF, "trailing JSON data")
	return v
}
func encoded(v any, indent bool) []byte {
	var b bytes.Buffer
	e := json.NewEncoder(&b)
	e.SetEscapeHTML(false)
	if indent {
		e.SetIndent("", "  ")
	}
	must(e.Encode(v))
	return bytes.TrimSuffix(b.Bytes(), []byte("\n"))
}
func writeNew(path string, v any) {
	must(os.MkdirAll(filepath.Dir(path), 0755))
	writeBytesNew(path, encoded(v, true))
}
func writeBytesNew(path string, b []byte) {
	f, e := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0644)
	must(e)
	_, e = f.Write(b)
	closeErr := f.Close()
	must(e)
	must(closeErr)
}
func hash(b []byte) string { s := sha256.Sum256(b); return hex.EncodeToString(s[:]) }

// canonical preserves Python json.dumps(sort_keys=True, ensure_ascii=False)
// separators and numeric representation so existing experiment IDs remain valid.
func canonical(v any) string {
	switch x := v.(type) {
	case nil:
		return "null"
	case bool:
		if x {
			return "true"
		}
		return "false"
	case string:
		return quoteJSON(x)
	case int:
		return strconv.Itoa(x)
	case int64:
		return strconv.FormatInt(x, 10)
	case float64:
		return pythonFloat(x)
	case json.Number:
		if !strings.ContainsAny(string(x), ".eE") {
			return string(x)
		}
		f, e := x.Float64()
		must(e)
		return pythonFloat(f)
	case []any:
		p := make([]string, len(x))
		for i, v := range x {
			p[i] = canonical(v)
		}
		return "[" + strings.Join(p, ", ") + "]"
	case map[string]any:
		keys := make([]string, 0, len(x))
		for k := range x {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		p := make([]string, 0, len(x))
		for _, k := range keys {
			p = append(p, canonical(k)+": "+canonical(x[k]))
		}
		return "{" + strings.Join(p, ", ") + "}"
	default:
		panic(fmt.Errorf("unsupported JSON value %T", v))
	}
}
func quoteJSON(s string) string {
	var b strings.Builder
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		default:
			if r < 0x20 {
				fmt.Fprintf(&b, `\u%04x`, r)
			} else {
				b.WriteRune(r)
			}
		}
	}
	b.WriteByte('"')
	return b.String()
}
func pythonFloat(f float64) string {
	require(!math.IsNaN(f) && !math.IsInf(f, 0), "nonfinite JSON number")
	s := strconv.FormatFloat(f, 'e', -1, 64)
	parts := strings.Split(s, "e")
	exp, e := strconv.Atoi(parts[1])
	must(e)
	if exp >= -4 && exp < 16 {
		s = strconv.FormatFloat(f, 'f', -1, 64)
		if !strings.Contains(s, ".") {
			s += ".0"
		}
		return s
	}
	return s
}
func digest(v any) string { return hash([]byte(canonical(v))) }
func same(a, b any) bool  { return canonical(a) == canonical(b) }
func clone(m object) object {
	out := object{}
	for k, v := range m {
		out[k] = v
	}
	return out
}
func exists(path string) bool { _, e := os.Lstat(path); return e == nil }
func regularDir(path string) {
	s, e := os.Lstat(path)
	must(e)
	require(s.IsDir() && s.Mode()&os.ModeSymlink == 0, "must be a regular directory")
}
func within(path, root string) bool {
	p, e := filepath.Abs(path)
	must(e)
	r, e := filepath.EvalSymlinks(root)
	must(e)
	r, e = filepath.Abs(r)
	must(e) // Resolve an existing archive ancestor as Path.resolve does.
	suffix := []string{}
	for !exists(p) {
		suffix = append(suffix, filepath.Base(p))
		next := filepath.Dir(p)
		require(next != p, "invalid path")
		p = next
	}
	p, e = filepath.EvalSymlinks(p)
	must(e)
	for i := len(suffix) - 1; i >= 0; i-- {
		p = filepath.Join(p, suffix[i])
	}
	rel, e := filepath.Rel(r, p)
	must(e)
	return rel == "." || (!strings.HasPrefix(rel, ".."+string(os.PathSeparator)) && rel != "..")
}
func relativePath(v any) bool {
	s, ok := v.(string)
	if !ok || s == "" || filepath.IsAbs(s) {
		return false
	}
	for _, p := range strings.Split(filepath.ToSlash(s), "/") {
		if p == ".." {
			return false
		}
	}
	return true
}
func fileDigests(root string) object {
	regularDir(root)
	result := object{}
	must(filepath.WalkDir(root, func(path string, d os.DirEntry, e error) error {
		must(e)
		if path == root {
			return nil
		}
		rel, e := filepath.Rel(root, path)
		must(e)
		if d.Name() == ".git" || d.Name() == "__pycache__" {
			if d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		require(d.Type()&os.ModeSymlink == 0, "symbolic links are not supported")
		info, e := d.Info()
		must(e)
		if info.Mode().IsRegular() {
			data, e := os.ReadFile(path)
			must(e)
			result[filepath.ToSlash(rel)] = object{"sha256": hash(data), "executable": info.Mode()&0111 != 0}
		} else {
			require(info.IsDir(), "only regular files and directories are supported")
		}
		return nil
	}))
	return result
}
func copyFile(source, target string) {
	info, e := os.Lstat(source)
	must(e)
	require(info.Mode().IsRegular(), "only regular files are supported")
	must(os.MkdirAll(filepath.Dir(target), 0755))
	in, e := os.OpenFile(source, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
	must(e)
	defer in.Close()
	actual, e := in.Stat()
	must(e)
	require(os.SameFile(info, actual), "source changed during copy")
	out, e := os.OpenFile(target, os.O_CREATE|os.O_TRUNC|os.O_WRONLY|syscall.O_NOFOLLOW, info.Mode().Perm())
	must(e)
	_, e = io.Copy(out, in)
	closeErr := out.Close()
	must(e)
	must(closeErr)
	must(os.Chmod(target, info.Mode().Perm()))
}
func copyTree(source, target string, preserveLinks bool) {
	regularDir(source)
	must(os.MkdirAll(target, 0755))
	must(filepath.WalkDir(source, func(path string, d os.DirEntry, e error) error {
		must(e)
		if path == source {
			return nil
		}
		if !preserveLinks && (d.Name() == ".git" || d.Name() == "__pycache__") {
			if d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		rel, e := filepath.Rel(source, path)
		must(e)
		dest := filepath.Join(target, rel)
		if d.Type()&os.ModeSymlink != 0 {
			require(preserveLinks, "symbolic links are not supported")
			link, e := os.Readlink(path)
			must(e)
			must(os.Symlink(link, dest))
		} else if d.IsDir() {
			must(os.MkdirAll(dest, 0755))
		} else {
			copyFile(path, dest)
		}
		return nil
	}))
}
func candidate(archive, ident string) object {
	identifier(ident)
	folder := filepath.Join(archive, "candidates", ident)
	r := obj(read(filepath.Join(folder, "candidate.json")))
	require(digest(r) == ident, "candidate metadata digest mismatch")
	require(same(fileDigests(filepath.Join(folder, "files")), r["files"]), "candidate file digest mismatch")
	return r
}
func snapshot(archive, source string, metadata object) string {
	regularDir(source)
	require(!within(archive, source), "archive must be outside source")
	fields(metadata, []string{"parents", "hypothesis", "strategy"}, "without_skill")
	if v, ok := metadata["without_skill"]; ok {
		_, ok = v.(bool)
		require(ok, "without_skill must be boolean")
	}
	parents := array(metadata["parents"])
	for _, k := range []string{"hypothesis", "strategy"} {
		require(nonempty(metadata[k]), k+" is required")
	}
	for _, p := range parents {
		candidate(archive, text(p))
	}
	files := fileDigests(source)
	r := object{"version": 1, "without_skill": false, "files": files}
	for k, v := range metadata {
		r[k] = v
	}
	ident := digest(r)
	dest := filepath.Join(archive, "candidates", ident)
	if exists(dest) {
		candidate(archive, ident)
		return ident
	}
	must(os.MkdirAll(filepath.Dir(dest), 0755))
	temp, e := os.MkdirTemp(filepath.Dir(dest), "snapshot-")
	must(e)
	defer os.RemoveAll(temp)
	stage := filepath.Join(temp, "candidate")
	must(os.MkdirAll(filepath.Join(stage, "files"), 0755))
	for relative := range files {
		copyFile(filepath.Join(source, relative), filepath.Join(stage, "files", relative))
	}
	require(same(fileDigests(filepath.Join(stage, "files")), files) && same(fileDigests(source), files), "source changed during snapshot")
	writeNew(filepath.Join(stage, "candidate.json"), r)
	must(os.Rename(stage, dest))
	return ident
}
func validateSuite(s object) {
	fields(s, []string{"version", "mode", "entrypoint", "cases"})
	version, isNumber := number(s["version"])
	if value, isBool := s["version"].(bool); isBool {
		isNumber = true
		if value {
			version = 1
		} else {
			version = 0
		}
	}
	require(isNumber && version == 1, "unsupported suite version")
	require(oneOf(s["mode"], "execution", "discovery"), "invalid mode")
	require(s["entrypoint"] == nil || relativePath(s["entrypoint"]), "invalid entrypoint")
	cases := array(s["cases"])
	require(len(cases) > 0, "cases are required")
	ids := map[string]bool{}
	for _, raw := range cases {
		c := obj(raw)
		fields(c, []string{"id", "prompt", "split", "checks"})
		id := identifier(c["id"])
		require(!ids[id], "duplicate case id")
		ids[id] = true
		require(nonempty(c["prompt"]), "prompt is required")
		require(oneOf(c["split"], "train", "validation", "test"), "invalid split")
		checks := array(c["checks"])
		require(len(checks) > 0, "checks are required")
		seen := map[string]bool{}
		for _, raw := range checks {
			ch := obj(raw)
			fields(ch, []string{"id", "criterion", "required"})
			id := identifier(ch["id"])
			require(!seen[id], "duplicate check id")
			seen[id] = true
			require(nonempty(ch["criterion"]), "criterion is required")
			_, ok := ch["required"].(bool)
			require(ok, "required must be boolean")
		}
	}
}
func caseByID(s object, id string) object {
	for _, c := range array(s["cases"]) {
		if obj(c)["id"] == id {
			return obj(c)
		}
	}
	panic(fmt.Errorf("unknown case"))
}
func validateChecks(checks object, c object) {
	expected := map[string]bool{}
	for _, raw := range array(c["checks"]) {
		expected[text(obj(raw)["id"])] = true
	}
	for k, v := range checks {
		require(expected[k], "unknown check id")
		ch := obj(v)
		fields(ch, []string{"verdict", "evidence"})
		require(oneOf(ch["verdict"], "pass", "fail", "unknown"), "invalid verdict")
		require(nonempty(ch["evidence"]), "evidence is required")
	}
}
func integer(v any) (int, bool) {
	switch n := v.(type) {
	case int:
		return n, true
	case json.Number:
		i, e := strconv.Atoi(string(n))
		return i, e == nil
	}
	return 0, false
}
func number(v any) (float64, bool) {
	switch n := v.(type) {
	case int:
		return float64(n), true
	case float64:
		return n, true
	case json.Number:
		f, e := n.Float64()
		return f, e == nil
	}
	return 0, false
}
func compare(s object, records []object, baseline, proposed, split string) object {
	validateSuite(s)
	require(baseline != proposed, "distinct candidates are required")
	cases := []object{}
	for _, raw := range array(s["cases"]) {
		c := obj(raw)
		if c["split"] == split {
			cases = append(cases, c)
		}
	}
	require(len(cases) > 0, "split has no cases")
	type key struct {
		candidate, caseID string
		repeat            int
	}
	indexed := map[key]object{}
	envs := map[string]bool{}
	for _, r := range records {
		if r["candidate"] != baseline && r["candidate"] != proposed {
			continue
		}
		require(r["suite"] == digest(s), "suite version mismatch")
		c := caseByID(s, text(r["case"]))
		if c["split"] != split {
			continue
		}
		repeat, ok := integer(r["repeat"])
		require(ok && repeat > 0, "repeat must be positive")
		require(oneOf(r["status"], "completed", "error", "timeout"), "invalid run status")
		require(nonempty(r["environment"]), "environment is required")
		envs[text(r["environment"])] = true
		validateChecks(obj(r["checks"]), c)
		for _, v := range obj(r["metrics"]) {
			if v == nil {
				continue
			}
			n, ok := number(v)
			require(ok && !math.IsNaN(n) && !math.IsInf(n, 0) && n >= 0, "metrics must be nonnegative numbers or null")
		}
		k := key{text(r["candidate"]), text(r["case"]), repeat}
		_, duplicate := indexed[k]
		require(!duplicate, "duplicate run")
		identifier(r["id"])
		indexed[k] = r
	}
	require(len(envs) <= 1, "environment mismatch")
	counts := object{"improved": 0, "regressed": 0, "unchanged": 0, "unknown": 0}
	rows := []any{}
	deltas := map[string][]any{"duration_seconds": {}, "tokens": {}}
	requiredRegression := false
	for _, c := range cases {
		id := text(c["id"])
		repeats := map[int]bool{}
		for k := range indexed {
			if k.caseID == id {
				repeats[k.repeat] = true
			}
		}
		if len(repeats) == 0 {
			repeats[1] = true
		}
		ordered := []int{}
		for r := range repeats {
			ordered = append(ordered, r)
		}
		sort.Ints(ordered)
		for _, repeat := range ordered {
			old, new := indexed[key{baseline, id, repeat}], indexed[key{proposed, id, repeat}]
			verdict := func(r object, check string) string {
				if r == nil || r["status"] != "completed" {
					return "unknown"
				}
				v, ok := obj(r["checks"])[check]
				if !ok {
					return "unknown"
				}
				return text(obj(v)["verdict"])
			}
			runID := func(r object) any {
				if r == nil {
					return nil
				}
				return r["id"]
			}
			for _, raw := range array(c["checks"]) {
				check := obj(raw)
				before, after := verdict(old, text(check["id"])), verdict(new, text(check["id"]))
				outcome := "unchanged"
				if before == "unknown" || after == "unknown" {
					outcome = "unknown"
				} else if before != after {
					outcome = "regressed"
					if after == "pass" {
						outcome = "improved"
					}
				}
				counts[outcome] = counts[outcome].(int) + 1
				requiredRegression = requiredRegression || (outcome == "regressed" && check["required"].(bool))
				rows = append(rows, object{"case": id, "repeat": repeat, "check": check["id"], "baseline_run": runID(old), "candidate_run": runID(new), "before": before, "after": after, "outcome": outcome})
			}
			for metric := range deltas {
				var delta any
				if old != nil && new != nil && old["status"] == "completed" && new["status"] == "completed" {
					a, b := obj(old["metrics"])[metric], obj(new["metrics"])[metric]
					if a != nil && b != nil {
						av, _ := number(a)
						bv, _ := number(b)
						delta = bv - av
					}
				}
				deltas[metric] = append(deltas[metric], delta)
			}
		}
	}
	assessment := "unchanged"
	switch {
	case requiredRegression:
		assessment = "regressed"
	case counts["unknown"].(int) > 0:
		assessment = "inconclusive"
	case counts["regressed"].(int) > 0:
		assessment = "tradeoff"
	case counts["improved"].(int) > 0:
		assessment = "improved"
	}
	metrics := object{}
	for k, values := range deltas {
		valid := true
		sum := 0.0
		for _, v := range values {
			if v == nil {
				valid = false
			} else {
				sum += v.(float64)
			}
		}
		metrics[k+"_delta"] = nil
		if valid {
			metrics[k+"_delta"] = sum / float64(len(values))
		}
	}
	ids := []string{}
	rd := object{}
	for _, r := range indexed {
		id := text(r["id"])
		ids = append(ids, id)
		rd[id] = digest(r)
	}
	sort.Strings(ids)
	runs := []any{}
	for _, id := range ids {
		runs = append(runs, id)
	}
	var environment any
	for e := range envs {
		environment = e
	}
	return object{"baseline": baseline, "candidate": proposed, "suite": digest(s), "split": split, "environment": environment, "runs": runs, "run_digests": rd, "assessment": assessment, "counts": counts, "rows": rows, "metrics": metrics}
}
func execute(archive, ident string, s object, caseID, fixture string, config object, repeat int, timeout float64) string {
	validateSuite(s)
	cr := candidate(archive, ident)
	require(repeat > 0, "repeat must be positive")
	require(timeout > 0 && !math.IsNaN(timeout) && !math.IsInf(timeout, 0), "invalid timeout")
	fields(config, []string{"model", "reasoning", "context"}, "disabled_skills")
	for _, k := range []string{"model", "reasoning", "context"} {
		require(nonempty(config[k]), "config values are required")
	}
	disabled := []string{}
	if v, ok := config["disabled_skills"]; ok {
		for _, raw := range array(v) {
			p := text(raw)
			require(filepath.IsAbs(p) && filepath.Base(p) == "SKILL.md", "disabled_skills must contain absolute SKILL.md paths")
			disabled = append(disabled, p)
		}
	}
	sort.Strings(disabled)
	disabledJSON := []any{}
	for i, p := range disabled {
		if i == 0 || p != disabled[i-1] {
			disabledJSON = append(disabledJSON, p)
		}
	}
	config = clone(config)
	config["disabled_skills"] = disabledJSON
	c := caseByID(s, caseID)
	regularDir(fixture)
	require(!within(archive, fixture), "archive must be outside fixture")
	fixtureFiles := fileDigests(fixture)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	version, e := exec.CommandContext(ctx, "codex", "--version").Output()
	must(e)
	environment := clone(config)
	environment["cli"] = strings.TrimSpace(string(version))
	environment["fixture"] = fixtureFiles
	environment["sandbox"] = "workspace-write"
	environment["adapter"] = hash(adapterSource)
	idBytes := make([]byte, 16)
	_, e = rand.Read(idBytes)
	must(e)
	absArchive, e := filepath.Abs(archive)
	must(e)
	folder := filepath.Join(absArchive, "runs", hex.EncodeToString(idBytes))
	must(os.MkdirAll(folder, 0755))
	writeNew(filepath.Join(folder, "suite.json"), s)
	writeNew(filepath.Join(folder, "environment.json"), environment)
	temp, e := os.MkdirTemp("", "skill-eval-")
	must(e)
	defer os.RemoveAll(temp)
	work := filepath.Join(temp, "workspace")
	copyTree(fixture, work, false)
	require(same(fileDigests(work), fixtureFiles), "fixture changed during copy")
	copyTree(filepath.Join(archive, "candidates", ident, "files"), work, false)
	prompt := text(c["prompt"])
	entry := s["entrypoint"]
	if s["mode"] == "execution" && entry != nil {
		target := filepath.Join(work, text(entry))
		without, _ := cr["without_skill"].(bool)
		if without {
			require(!exists(target), "without_skill candidate still contains entrypoint")
		} else {
			info, e := os.Stat(target)
			require(e == nil && info.Mode().IsRegular(), "execution entrypoint is missing or not a file")
			prompt = "Use the instructions in " + text(entry) + " for this task.\n\n" + prompt
		}
	}
	must(os.WriteFile(filepath.Join(folder, "prompt.txt"), []byte(prompt), 0644))
	answer := filepath.Join(temp, "answer.txt")
	command := []string{"codex", "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check", "--json", "--color", "never", "-s", "workspace-write", "-m", text(config["model"]), "-c", "model_reasoning_effort=" + canonical(config["reasoning"]), "-c", `approval_policy="never"`, "-C", work, "-o", answer, "-"}
	if len(disabledJSON) > 0 {
		pieces := []string{}
		for _, p := range disabledJSON {
			pieces = append(pieces, "{path="+canonical(p)+",enabled=false}")
		}
		command = append(command[:2], append([]string{"-c", "skills.config=[" + strings.Join(pieces, ",") + "]"}, command[2:]...)...)
	}
	commandJSON := []any{}
	for _, arg := range command {
		commandJSON = append(commandJSON, arg)
	}
	writeNew(filepath.Join(folder, "command.json"), commandJSON)
	out, e := os.Create(filepath.Join(folder, "trace.jsonl"))
	must(e)
	errout, e := os.Create(filepath.Join(folder, "stderr.txt"))
	if e != nil {
		out.Close()
		must(e)
	}
	started := time.Now()
	status := "error"
	var returncode any
	cmd := exec.Command(command[0], command[1:]...)
	cmd.Dir = work
	cmd.Stdout = out
	cmd.Stderr = errout
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	// Own both pipe ends: Cmd.Wait must not close the writer before the prompt
	// goroutine has reported its result. A child closing stdin produces EPIPE,
	// which Python's communicate also suppresses.
	stdinReader, stdin, pipeErr := os.Pipe()
	must(pipeErr)
	cmd.Stdin = stdinReader
	processSucceeded := false
	if e = cmd.Start(); e != nil {
		stdinReader.Close()
		stdin.Close()
		fmt.Fprint(errout, e)
	} else {
		must(stdinReader.Close())
		timedOut, waitErr, writeErr := communicate(cmd, stdin, prompt, time.Duration(timeout*float64(time.Second)))
		if timedOut {
			status = "timeout"
		}
		if writeErr != nil {
			fmt.Fprint(errout, writeErr)
		}
		processSucceeded = !timedOut && waitErr == nil && writeErr == nil
		returncode = cmd.ProcessState.ExitCode()
		if ws, ok := cmd.ProcessState.Sys().(syscall.WaitStatus); ok && ws.Signaled() {
			returncode = -int(ws.Signal())
		}
	}
	must(out.Close())
	must(errout.Close())
	duration := time.Since(started).Seconds()
	if info, e := os.Lstat(answer); e == nil && info.Mode().IsRegular() {
		copyFile(answer, filepath.Join(folder, "answer.txt"))
		if processSucceeded {
			status = "completed"
		}
	}
	copyTree(work, filepath.Join(folder, "workspace"), true)
	tokens, measured := 0, false
	trace, e := os.ReadFile(filepath.Join(folder, "trace.jsonl"))
	must(e)
	for _, line := range bytes.Split(trace, []byte("\n")) {
		d := json.NewDecoder(bytes.NewReader(line))
		d.UseNumber()
		var event object
		if d.Decode(&event) != nil || event["type"] != "turn.completed" {
			continue
		}
		usage, ok := event["usage"].(map[string]any)
		if !ok {
			continue
		}
		a, aok := integer(usage["input_tokens"])
		b, bok := integer(usage["output_tokens"])
		if aok && bok && a >= 0 && b >= 0 {
			tokens += a + b
			measured = true
		}
	}
	var tokenValue any
	if measured {
		tokenValue = tokens
	}
	entrypoint := entry
	if cr["without_skill"] == true {
		entrypoint = nil
	}
	r := object{"id": filepath.Base(folder), "candidate": ident, "suite": digest(s), "case": caseID, "repeat": repeat, "entrypoint": entrypoint, "environment": digest(environment), "status": status, "returncode": returncode, "checks": object{}, "metrics": object{"duration_seconds": duration, "tokens": tokenValue}, "artifacts": artifactDigests(folder)}
	writeNew(filepath.Join(folder, "run.json"), r)
	writeNew(filepath.Join(folder, "run-digest.json"), digest(r))
	return folder
}

// communicate waits for both the process and stdin writer on every path.
// Timeout and non-EPIPE communication errors kill the process group before reaping.
func communicate(cmd *exec.Cmd, stdin io.WriteCloser, prompt string, timeout time.Duration) (timedOut bool, waitErr, writeErr error) {
	written := make(chan error, 1)
	go func() {
		_, err := io.WriteString(stdin, prompt)
		closeErr := stdin.Close()
		if err == nil {
			err = closeErr
		}
		if errors.Is(err, syscall.EPIPE) {
			err = nil
		}
		written <- err
	}()
	waited := make(chan error, 1)
	go func() { waited <- cmd.Wait() }()
	timer := time.NewTimer(timeout)
	defer timer.Stop()
	deadline := timer.C
	for written != nil || waited != nil {
		select {
		case writeErr = <-written:
			written = nil
			if writeErr != nil {
				_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
			}
		case waitErr = <-waited:
			waited = nil
		case <-deadline:
			timedOut = true
			deadline = nil
			_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		}
	}
	return
}

func artifactDigests(folder string) object {
	result := object{}
	must(filepath.WalkDir(folder, func(path string, d os.DirEntry, e error) error {
		must(e)
		if path == folder {
			return nil
		}
		rel, e := filepath.Rel(folder, path)
		must(e)
		rel = filepath.ToSlash(rel)
		if rel == "run.json" || rel == "run-digest.json" || rel == "grading.json" {
			return nil
		}
		if d.Type()&os.ModeSymlink != 0 {
			link, e := os.Readlink(path)
			must(e)
			result[rel] = object{"link": link}
		} else {
			info, e := d.Info()
			must(e)
			if info.Mode().IsRegular() {
				b, e := os.ReadFile(path)
				must(e)
				result[rel] = object{"sha256": hash(b), "executable": info.Mode()&0111 != 0}
			}
		}
		return nil
	}))
	return result
}
func loadRun(folder string) object {
	r := obj(read(filepath.Join(folder, "run.json")))
	require(r["id"] == filepath.Base(folder), "run id mismatch")
	require(digest(r) == read(filepath.Join(folder, "run-digest.json")), "run digest mismatch")
	require(same(artifactDigests(folder), r["artifacts"]), "artifact digest mismatch")
	if exists(filepath.Join(folder, "grading.json")) {
		g := obj(read(filepath.Join(folder, "grading.json")))
		require(g["run_digest"] == digest(r), "grading run digest mismatch")
		r["checks"] = g["checks"]
	}
	return r
}
func grade(folder string, g object) {
	r := loadRun(folder)
	fields(g, []string{"grader", "checks"})
	require(nonempty(g["grader"]), "grader is required")
	s := obj(read(filepath.Join(folder, "suite.json")))
	c := caseByID(s, text(r["case"]))
	checks := obj(g["checks"])
	validateChecks(checks, c)
	require(len(checks) == len(array(c["checks"])), "all checks must be graded")
	g = clone(g)
	g["run_digest"] = digest(r)
	writeNew(filepath.Join(folder, "grading.json"), g)
}
func remember(archive string, n object) string {
	fields(n, []string{"hypothesis", "scope", "status", "support", "counterevidence", "directions"})
	for _, k := range []string{"hypothesis", "scope"} {
		require(nonempty(n[k]), k+" is required")
	}
	require(oneOf(n["status"], "active", "refuted"), "invalid diagnosis status")
	evidence := object{}
	for _, k := range []string{"support", "counterevidence"} {
		for _, raw := range array(n[k]) {
			id := identifier(raw)
			folder := filepath.Join(archive, "runs", id)
			r := loadRun(folder)
			s := obj(read(filepath.Join(folder, "suite.json")))
			c := caseByID(s, text(r["case"]))
			require(c["split"] == "train", "momentum accepts train evidence only")
			require(r["status"] == "completed" && len(obj(r["checks"])) > 0, "graded completed evidence is required")
			evidence[id] = digest(r)
		}
	}
	require(len(evidence) > 0, "execution evidence is required")
	directions := array(n["directions"])
	require(len(directions) > 0, "directions are required")
	for _, raw := range directions {
		d := obj(raw)
		fields(d, []string{"operation", "layer", "path", "reason"})
		require(oneOf(d["operation"], "add", "delete", "replace", "move"), "invalid operation")
		require(oneOf(d["layer"], "metadata", "body", "reference", "script", "configuration"), "invalid layer")
		for _, k := range []string{"path", "reason"} {
			require(nonempty(d[k]), k+" is required")
		}
		require(relativePath(d["path"]), "invalid direction path")
	}
	r := clone(n)
	r["version"] = 1
	r["evidence_digests"] = evidence
	id := digest(r)
	path := filepath.Join(archive, "diagnoses", id+".json")
	if exists(path) {
		require(same(read(path), r), "diagnosis digest mismatch")
	} else {
		writeNew(path, r)
	}
	return id
}
func report(folders []string, comparison object) string {
	actual := []string{}
	for _, f := range folders {
		actual = append(actual, filepath.Base(f))
	}
	sort.Strings(actual)
	expected := []string{}
	for _, v := range array(comparison["runs"]) {
		expected = append(expected, text(v))
	}
	sort.Strings(expected)
	require(strings.Join(actual, "\n") == strings.Join(expected, "\n"), "report run selection mismatch")
	digests := object{}
	for _, f := range folders {
		digests[filepath.Base(f)] = digest(loadRun(f))
	}
	require(same(digests, comparison["run_digests"]), "report run digest mismatch")
	esc := html.EscapeString
	var sections strings.Builder
	for _, f := range folders {
		r := loadRun(f)
		answer := "(no answer)"
		if exists(filepath.Join(f, "answer.txt")) {
			b, e := os.ReadFile(filepath.Join(f, "answer.txt"))
			must(e)
			answer = string(b)
		}
		prompt, e := os.ReadFile(filepath.Join(f, "prompt.txt"))
		must(e)
		summary := object{}
		for _, k := range []string{"case", "repeat", "status", "metrics", "checks"} {
			summary[k] = r[k]
		}
		abs, e := filepath.Abs(filepath.Join(f, "workspace"))
		must(e)
		link := (&url.URL{Scheme: "file", Path: abs}).String()
		id := filepath.Base(f)
		short := id
		if len(short) > 8 {
			short = short[:8]
		}
		fmt.Fprintf(&sections, `<section><h2>%s / %s</h2><h3>依頼</h3><pre>%s</pre><h3>成果物</h3><pre>%s</pre><h3>採点と測定</h3><pre>%s</pre><details><summary>実行記録と版</summary><pre>%s</pre></details><p><a href="%s">作業結果のフォルダ</a></p><label>評価コメント<textarea data-run="%s"></textarea></label></section>`, esc(text(r["case"])), esc(short), esc(string(prompt)), esc(answer), esc(string(encoded(summary, true))), esc(string(encoded(r, true))), esc(link), esc(id))
	}
	return `<!doctype html><html lang="ja"><meta charset="utf-8"><title>Skill 評価</title><style>body{max-width:1000px;margin:40px auto;font:16px system-ui;padding:0 20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f7;padding:16px}textarea{display:block;width:100%;min-height:90px}section{margin:40px 0}button{padding:12px}</style><h1>Skill 評価</h1><p>この比較は観測結果です。採用判断と統計的な確実性は別に評価します。</p><pre>` + esc(string(encoded(comparison, true))) + `</pre>` + sections.String() + `<button id="save">コメントを JSON へ保存</button><script>document.getElementById("save").onclick=()=>{const reviews=[...document.querySelectorAll("textarea")].map(e=>({run:e.dataset.run,comment:e.value}));const u=URL.createObjectURL(new Blob([JSON.stringify({reviews},null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=u;a.download="feedback.json";a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);};</script></html>`
}

type argumentError struct{ message string }

func (e argumentError) Error() string { return e.message }
func argumentRequire(ok bool, message string) {
	if !ok {
		panic(argumentError{message})
	}
}

// parse accepts argparse's --runs path... form without a custom launcher.
func parse(args []string, required []string, optional ...string) map[string][]string {
	allowed := map[string]bool{}
	for _, k := range append(append([]string{}, required...), optional...) {
		allowed[k] = true
	}
	values := map[string][]string{}
	for i := 0; i < len(args); {
		raw := args[i]
		key, inline, hasInline := strings.Cut(strings.TrimPrefix(raw, "--"), "=")
		argumentRequire(strings.HasPrefix(raw, "--") && allowed[key], "unknown argument: "+raw)
		i++
		argumentRequire(values[key] == nil, "duplicate argument: "+key)
		if hasInline {
			values[key] = []string{inline}
			continue
		}
		start := i
		for i < len(args) && !strings.HasPrefix(args[i], "--") {
			i++
			if key != "runs" {
				break
			}
		}
		argumentRequire(i > start, "missing value: "+key)
		values[key] = args[start:i]
	}
	for _, k := range required {
		argumentRequire(len(values[k]) > 0, "missing argument: --"+k)
	}
	return values
}
func cli(args []string) (code int) {
	defer func() {
		if e := recover(); e != nil {
			if _, ok := e.(argumentError); ok {
				fmt.Fprintln(os.Stderr, "usage: workbench {snapshot,run,grade,compare,report,remember} [options]")
				fmt.Fprintln(os.Stderr, "workbench: error:", e)
				code = 2
			} else {
				fmt.Fprintln(os.Stderr, string(encoded(object{"error": fmt.Sprint(e)}, false)))
				code = 1
			}
		}
	}()
	argumentRequire(len(args) > 0, "a command is required")
	if args[0] == "--help" || args[0] == "-h" {
		fmt.Println("workbench <snapshot|run|grade|compare|report|remember> [options]\nLocal experiment storage and Codex execution. See references/experiment-contract.md.")
		return 0
	}
	command := args[0]
	argumentRequire(oneOf(command, "snapshot", "run", "grade", "compare", "report", "remember"), "unknown command: "+command)
	if len(args) == 2 && (args[1] == "--help" || args[1] == "-h") {
		fmt.Println("workbench " + command + " — see references/experiment-contract.md for options")
		return 0
	}
	var v map[string][]string
	switch command {
	case "snapshot":
		v = parse(args[1:], []string{"archive", "source", "metadata"})
	case "run":
		v = parse(args[1:], []string{"archive", "candidate", "suite", "case", "fixture", "config"}, "repeat", "timeout")
	case "grade":
		v = parse(args[1:], []string{"run", "grading"})
	case "compare":
		v = parse(args[1:], []string{"suite", "runs", "baseline", "candidate", "split", "output"})
	case "report":
		v = parse(args[1:], []string{"runs", "comparison", "output"})
	case "remember":
		v = parse(args[1:], []string{"archive", "diagnosis"})
	default:
		panic(argumentError{"unknown command: " + command})
	}
	get := func(k string) string {
		if len(v[k]) == 0 {
			return ""
		}
		return v[k][0]
	}
	switch command {
	case "snapshot":
		fmt.Println(snapshot(get("archive"), get("source"), obj(read(get("metadata")))))
	case "run":
		repeat := 1
		timeout := 600.0
		if get("repeat") != "" {
			n, e := strconv.Atoi(get("repeat"))
			argumentRequire(e == nil, "invalid repeat")
			repeat = n
		}
		if get("timeout") != "" {
			n, e := strconv.ParseFloat(get("timeout"), 64)
			argumentRequire(e == nil, "invalid timeout")
			timeout = n
		}
		fmt.Println(execute(get("archive"), get("candidate"), obj(read(get("suite"))), get("case"), get("fixture"), obj(read(get("config"))), repeat, timeout))
	case "grade":
		grade(get("run"), obj(read(get("grading"))))
		fmt.Println(filepath.Join(get("run"), "grading.json"))
	case "compare":
		argumentRequire(oneOf(get("split"), "train", "validation", "test"), "invalid split")
		records := []object{}
		for _, f := range v["runs"] {
			records = append(records, loadRun(f))
		}
		writeNew(get("output"), compare(obj(read(get("suite"))), records, get("baseline"), get("candidate"), get("split")))
		fmt.Println(get("output"))
	case "report":
		rendered := report(v["runs"], obj(read(get("comparison"))))
		writeBytesNew(get("output"), []byte(rendered))
		fmt.Println(get("output"))
	case "remember":
		fmt.Println(remember(get("archive"), obj(read(get("diagnosis")))))
	}
	return 0
}
func main() { os.Exit(cli(os.Args[1:])) }
