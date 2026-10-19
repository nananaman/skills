// check-skill-inventory checks the source skill layout and Markdown resources.
package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strings"
	"unicode/utf8"
)

type finding struct {
	Code    string `json:"code"`
	Path    string `json:"path"`
	Message string `json:"message"`
}

var ignored = map[string]bool{".agents": true, ".claude": true, ".git": true, "_build": true, "apm_modules": true, "node_modules": true}
var controls = map[string]bool{}
var linkPattern = regexp.MustCompile(`\[[^\]]*\]\(([^)]+)\)`)
var headingPattern = regexp.MustCompile(`^\s{0,3}#{1,6}(?:[ \t]+|$)(.*)$`)
var fencePattern = regexp.MustCompile("^\\s{0,3}(`{3,}|~{3,})")
var closingHeading = regexp.MustCompile(`[ \t]+#+[ \t]*$`)

func init() {
	for _, s := range []string{"workflow", "completion", "safety", "output", "contract", "lifecycle", "context discovery", "branch router", "change rules", "failure handling", "when to use", "when not to use", "prerequisites", "progress", "authority boundary"} {
		controls[s] = true
	}
}
func lines(s string) []string {
	s = strings.ReplaceAll(s, "\r\n", "\n")
	s = strings.ReplaceAll(s, "\r", "\n")
	return strings.Split(s, "\n")
}
func readMarkdown(path string) ([]byte, error) {
	data, err := os.ReadFile(path)
	if err == nil && !utf8.Valid(data) {
		return nil, fmt.Errorf("%s: Markdown is not valid UTF-8", path)
	}
	return data, err
}
func frontmatter(path string) (map[string]string, []finding, error) {
	data, e := readMarkdown(path)
	if e != nil {
		return nil, nil, e
	}
	ls := lines(string(data))
	out := []finding{}
	m := map[string]string{}
	if len(ls) == 0 || strings.TrimSpace(ls[0]) != "---" {
		return m, []finding{{"frontmatter-missing", path, "先頭に YAML frontmatter がありません"}}, nil
	}
	end := -1
	for i := 1; i < len(ls); i++ {
		if strings.TrimSpace(ls[i]) == "---" {
			end = i
			break
		}
	}
	if end < 0 {
		return m, []finding{{"frontmatter-unclosed", path, "YAML frontmatter が閉じられていません"}}, nil
	}
	for i := 1; i < end; i++ {
		line := ls[i]
		if strings.TrimSpace(line) == "" || strings.HasPrefix(line, " ") || strings.HasPrefix(line, "\t") {
			continue
		}
		k, v, found := strings.Cut(line, ":")
		if !found {
			out = append(out, finding{"frontmatter-invalid-line", path, fmt.Sprintf("%d 行目を解釈できません", i+1)})
			continue
		}
		m[strings.TrimSpace(k)] = strings.Trim(strings.TrimSpace(v), "\"'")
	}
	for _, required := range []string{"name", "description"} {
		if m[required] == "" {
			out = append(out, finding{"frontmatter-required", path, "frontmatter に " + required + ": が必要です"})
		}
	}
	return m, out, nil
}
func realpath(p string) string {
	p, _ = filepath.Abs(p)
	if r, e := filepath.EvalSymlinks(p); e == nil {
		return r
	}
	parent := filepath.Dir(p)
	if parent != p {
		return filepath.Join(realpath(parent), filepath.Base(p))
	}
	return p
}
func inRoot(root, p string) bool {
	r, e := filepath.Rel(root, p)
	return e == nil && r != ".." && !strings.HasPrefix(r, ".."+string(filepath.Separator))
}
func relative(root, p string) string { r, _ := filepath.Rel(root, p); return filepath.ToSlash(r) }
func markdownPaths(root string) ([]string, error) {
	out := []string{}
	e := filepath.WalkDir(root, func(p string, d fs.DirEntry, e error) error {
		if e != nil {
			return e
		}
		if p != root && d.IsDir() && ignored[d.Name()] {
			return filepath.SkipDir
		}
		if !d.IsDir() && strings.HasSuffix(d.Name(), ".md") {
			out = append(out, p)
		}
		return nil
	})
	sort.Strings(out)
	return out, e
}
func checkLinks(root, path string) ([]finding, error) {
	b, e := readMarkdown(path)
	if e != nil {
		return nil, e
	}
	out := []finding{}
	for _, m := range linkPattern.FindAllStringSubmatch(string(b), -1) {
		target := strings.SplitN(strings.TrimSpace(m[1]), "#", 2)[0]
		if target == "" || strings.HasPrefix(target, "http://") || strings.HasPrefix(target, "https://") || strings.HasPrefix(target, "mailto:") {
			continue
		}
		p := filepath.Join(filepath.Dir(path), target)
		if filepath.IsAbs(target) {
			p = target
		}
		p = realpath(p)
		if !inRoot(realpath(root), p) {
			out = append(out, finding{"link-outside-repository", relative(root, path), target})
			continue
		}
		if _, e := os.Stat(p); errors.Is(e, fs.ErrNotExist) {
			out = append(out, finding{"link-missing", relative(root, path), target})
		} else if e != nil {
			return nil, e
		}
	}
	return out, nil
}
func checkHeadings(root, path string) ([]finding, error) {
	b, e := readMarkdown(path)
	if e != nil {
		return nil, e
	}
	out := []finding{}
	active := ""
	for i, line := range lines(string(b)) {
		fence := fencePattern.FindStringSubmatchIndex(line)
		f := ""
		rest := ""
		if fence != nil {
			f = line[fence[2]:fence[3]]
			rest = line[fence[1]:]
		}
		if active != "" {
			if len(f) >= len(active) && f[0] == active[0] && strings.TrimSpace(rest) == "" {
				active = ""
			}
			continue
		}
		if f != "" && !(f[0] == '`' && strings.Contains(rest, "`")) {
			active = f
			continue
		}
		h := headingPattern.FindStringSubmatch(line)
		if h == nil {
			continue
		}
		text := strings.TrimSpace(closingHeading.ReplaceAllString(h[1], ""))
		if controls[strings.ToLower(text)] {
			out = append(out, finding{"english-control-heading", relative(root, path), fmt.Sprintf("%d 行目の制御見出しを日本語で書いてください: %s", i+1, text)})
		}
	}
	return out, nil
}
func check(root string) ([]string, []finding, error) {
	root = realpath(root)
	skills := []string{}
	out := []finding{}
	names := map[string]string{}
	allMD := map[string]bool{}
	promptMD := map[string]bool{}
	err := filepath.WalkDir(root, func(p string, d fs.DirEntry, e error) error {
		if e != nil {
			return e
		}
		if p != root && d.IsDir() && ignored[d.Name()] {
			return filepath.SkipDir
		}
		if d.Name() == "SKILL.md" && !d.IsDir() {
			skills = append(skills, p)
		}
		return nil
	})
	if err != nil {
		return nil, nil, err
	}
	sort.Strings(skills)
	for _, path := range skills {
		rel := relative(root, path)
		meta, f, e := frontmatter(path)
		if e != nil {
			return nil, nil, e
		}
		for _, v := range f {
			v.Path = rel
			out = append(out, v)
		}
		name := meta["name"]
		if name != "" {
			parts := strings.Split(rel, "/")
			leaf := filepath.Base(filepath.Dir(path))
			if len(parts) != 4 || parts[0] != "plugin" || parts[1] != "skills" {
				out = append(out, finding{"skill-layout-invalid", rel, "正本は plugin/skills/<name>/SKILL.md に置いてください"})
			} else if name != leaf {
				out = append(out, finding{"name-directory-mismatch", rel, fmt.Sprintf("name: '%s' は directory 名に対応しません（許可値: ['%s']）", name, leaf)})
			}
			if previous, exists := names[name]; exists {
				out = append(out, finding{"name-duplicate", rel, fmt.Sprintf("name: '%s' は %s と重複しています", name, relative(root, previous))})
			} else {
				names[name] = path
			}
		}
		for _, item := range []struct{ path, target string }{{filepath.Join(root, "README.md"), "./" + rel}, {filepath.Join(root, "plugin/README.md"), "./skills/" + filepath.Base(filepath.Dir(path)) + "/SKILL.md"}} {
			b, e := readMarkdown(item.path)
			if errors.Is(e, fs.ErrNotExist) {
				out = append(out, finding{"readme-missing", relative(root, item.path), "README.md がありません"})
			} else if e != nil {
				return nil, nil, e
			} else if !strings.Contains(string(b), item.target) {
				out = append(out, finding{"readme-skill-missing", relative(root, item.path), item.target + " への skill 導線がありません"})
			}
		}
		paths, e := markdownPaths(filepath.Dir(path))
		if e != nil {
			return nil, nil, e
		}
		for _, p := range paths {
			allMD[p] = true
			if filepath.Base(p) != "README.md" && filepath.Base(p) != "NOTICE.md" {
				promptMD[p] = true
			}
		}
	}
	allMD[filepath.Join(root, "README.md")] = true
	paths, e := filepath.Glob(filepath.Join(root, "*/README.md"))
	if e != nil {
		return nil, nil, e
	}
	for _, p := range paths {
		allMD[p] = true
	}
	// Keep link and prompt checks separate: README/NOTICE may use English headings.
	paths = []string{}
	for p := range allMD {
		paths = append(paths, p)
	}
	sort.Strings(paths)
	for _, p := range paths {
		info, e := os.Stat(p)
		if errors.Is(e, fs.ErrNotExist) {
			continue
		}
		if e != nil {
			return nil, nil, e
		}
		if !info.Mode().IsRegular() {
			continue
		}
		f, e := checkLinks(root, p)
		if e != nil {
			return nil, nil, e
		}
		out = append(out, f...)
	}
	paths = []string{}
	for p := range promptMD {
		paths = append(paths, p)
	}
	sort.Strings(paths)
	for _, p := range paths {
		f, e := checkHeadings(root, p)
		if e != nil {
			return nil, nil, e
		}
		out = append(out, f...)
	}
	sort.Slice(out, func(i, j int) bool {
		a, b := out[i], out[j]
		if a.Path != b.Path {
			return a.Path < b.Path
		}
		if a.Code != b.Code {
			return a.Code < b.Code
		}
		return a.Message < b.Message
	})
	return skills, out, nil
}
func run(args []string, out, stderr io.Writer) int {
	// Preserve the original script's default source checkout when launched
	// from another directory. Relocated/path-trimmed builds use explicit --root.
	defaultRoot := ""
	if _, source, _, ok := runtime.Caller(0); ok && filepath.IsAbs(source) {
		defaultRoot = filepath.Dir(filepath.Dir(filepath.Dir(source)))
	}
	f := flag.NewFlagSet("check-skill-inventory", flag.ContinueOnError)
	f.SetOutput(stderr)
	root := f.String("root", defaultRoot, "source repository root (default build source checkout)")
	asJSON := f.Bool("json", false, "JSON report")
	if e := f.Parse(args); e != nil {
		if errors.Is(e, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if f.NArg() != 0 {
		return 2
	}
	if *root == "" {
		fmt.Fprintln(stderr, "--root is required for path-trimmed builds")
		return 2
	}
	skills, findings, e := check(*root)
	if e != nil {
		fmt.Fprintln(stderr, e)
		return 1
	}
	if *asJSON {
		enc := json.NewEncoder(out)
		enc.SetEscapeHTML(false)
		enc.SetIndent("", "  ")
		_ = enc.Encode(map[string]any{"skills": len(skills), "findings": findings})
	} else {
		fmt.Fprintf(out, "skills: %d\n", len(skills))
		if len(findings) == 0 {
			fmt.Fprintln(out, "findings: 0")
		} else {
			for _, v := range findings {
				fmt.Fprintf(out, "%s: [%s] %s\n", v.Path, v.Code, v.Message)
			}
		}
	}
	if len(findings) > 0 {
		return 1
	}
	return 0
}
func main() { os.Exit(run(os.Args[1:], os.Stdout, os.Stderr)) }
