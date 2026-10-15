package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func write(t *testing.T, p, s string) {
	t.Helper()
	if e := os.MkdirAll(filepath.Dir(p), 0755); e != nil {
		t.Fatal(e)
	}
	if e := os.WriteFile(p, []byte(s), 0644); e != nil {
		t.Fatal(e)
	}
}
func fixture(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	write(t, filepath.Join(root, "README.md"), "# Skills\n")
	write(t, filepath.Join(root, "plugin/README.md"), "# Engineering\n")
	return root
}
func appendText(t *testing.T, p, s string) {
	t.Helper()
	b, e := os.ReadFile(p)
	if e != nil {
		t.Fatal(e)
	}
	write(t, p, string(b)+s)
}
func addSkill(t *testing.T, root, dir, name string) string {
	t.Helper()
	p := filepath.Join(root, "plugin/skills", dir, "SKILL.md")
	write(t, p, "---\nname: "+name+"\ndescription: example skill\n---\n\n# Example\n")
	appendText(t, filepath.Join(root, "README.md"), "["+name+"](./plugin/skills/"+dir+"/SKILL.md)\n")
	appendText(t, filepath.Join(root, "plugin/README.md"), "["+name+"](./skills/"+dir+"/SKILL.md)\n")
	return p
}
func codeSet(t *testing.T, root string) map[string]bool {
	t.Helper()
	_, f, e := check(root)
	if e != nil {
		t.Fatal(e)
	}
	codes := map[string]bool{}
	for _, v := range f {
		codes[v.Code] = true
	}
	return codes
}
func TestConsistentInventoryHasNoFindings(t *testing.T) {
	root := fixture(t)
	addSkill(t, root, "example", "example")
	s, f, e := check(root)
	if e != nil || len(s) != 1 || len(f) != 0 {
		t.Fatal(s, f, e)
	}
}
func TestNamespacedDirectoryMatchesName(t *testing.T) {
	root := fixture(t)
	addSkill(t, root, "sakura-cloud-eventbus", "sakura-cloud-eventbus")
	if f := codeSet(t, root); len(f) != 0 {
		t.Fatal(f)
	}
}
func TestSkillOutsideNativePluginIsReported(t *testing.T) {
	root := fixture(t)
	write(t, filepath.Join(root, "engineering/legacy/SKILL.md"), "---\nname: legacy\ndescription: Example\n---\n")
	if !codeSet(t, root)["skill-layout-invalid"] {
		t.Fatal("missing layout finding")
	}
}
func TestSupportingReferenceLinksAreChecked(t *testing.T) {
	root := fixture(t)
	p := addSkill(t, root, "example", "example")
	write(t, filepath.Join(filepath.Dir(p), "references/contract.md"), "[missing](./missing.md)\n")
	if !codeSet(t, root)["link-missing"] {
		t.Fatal("missing link finding")
	}
}
func TestFrontmatterFailuresRemainDistinct(t *testing.T) {
	for _, tc := range []struct{ name, content, code string }{{"missing", "# Example\n", "frontmatter-missing"}, {"unclosed", "---\nname: example\n", "frontmatter-unclosed"}, {"required", "---\nname: example\n---\n", "frontmatter-required"}, {"invalid line", "---\nname: example\ndescription: example\nbroken\n---\n", "frontmatter-invalid-line"}} {
		t.Run(tc.name, func(t *testing.T) {
			root := fixture(t)
			p := addSkill(t, root, "example", "example")
			write(t, p, tc.content)
			if !codeSet(t, root)[tc.code] {
				t.Fatal("missing", tc.code)
			}
		})
	}
}
func TestNameDirectoryMismatchIsReported(t *testing.T) {
	root := fixture(t)
	addSkill(t, root, "example", "different")
	if !codeSet(t, root)["name-directory-mismatch"] {
		t.Fatal("missing mismatch")
	}
}
func TestDuplicateNamesAreReported(t *testing.T) {
	root := fixture(t)
	addSkill(t, root, "first", "engineering-first")
	addSkill(t, root, "second", "engineering-first")
	if !codeSet(t, root)["name-duplicate"] {
		t.Fatal("missing duplicate")
	}
}
func TestMissingReadmeCoverageIsReported(t *testing.T) {
	root := fixture(t)
	addSkill(t, root, "example", "example")
	write(t, filepath.Join(root, "plugin/README.md"), "# Engineering\n")
	if !codeSet(t, root)["readme-skill-missing"] {
		t.Fatal("missing README coverage")
	}
}
func TestMissingReadmeIsReported(t *testing.T) {
	root := fixture(t)
	addSkill(t, root, "example", "example")
	if e := os.Remove(filepath.Join(root, "README.md")); e != nil {
		t.Fatal(e)
	}
	if !codeSet(t, root)["readme-missing"] {
		t.Fatal("missing README finding")
	}
}
func TestRelativeLinkValidation(t *testing.T) {
	for _, tc := range []struct{ name, target, code string }{{"missing", "./references/missing.md", "link-missing"}, {"escape", "../../../../outside.md", "link-outside-repository"}, {"external", "https://example.invalid/example#fragment", ""}, {"anchor", "#Example", ""}, {"mail", "mailto:example@example.invalid", ""}} {
		t.Run(tc.name, func(t *testing.T) {
			root := fixture(t)
			p := addSkill(t, root, "example", "example")
			appendText(t, p, "[link]("+tc.target+")\n")
			codes := codeSet(t, root)
			if tc.code != "" && !codes[tc.code] {
				t.Fatal(codes)
			}
			if tc.code == "" && len(codes) != 0 {
				t.Fatal(codes)
			}
		})
	}
}
func TestEnglishControlHeadingIsReportedInSkillAndReference(t *testing.T) {
	for _, relative := range []string{"SKILL.md", "references/contract.md"} {
		t.Run(relative, func(t *testing.T) {
			root := fixture(t)
			skill := addSkill(t, root, "example", "example")
			p := filepath.Join(filepath.Dir(skill), relative)
			if relative == "SKILL.md" {
				appendText(t, p, "\n## Workflow\n")
			} else {
				write(t, p, "# 契約\n\n## Completion\n")
			}
			if !codeSet(t, root)["english-control-heading"] {
				t.Fatal("missing heading finding")
			}
		})
	}
}
func TestHeadingAndFenceRules(t *testing.T) {
	for _, tc := range []struct {
		name, markdown string
		finding        bool
	}{{"technical headings", "\n## GitHub Tool Routing\n\n## TypeScript / JavaScript\n", false}, {"code block", "\n```md\n## Output\n```\n", false}, {"short fence cannot close long block", "\n````md\n```\n## Output\n````\n", false}, {"closing heading needs space", "\n## Output###\n", false}, {"closing heading with space", "\n## Output ###\n", true}, {"backtick invalidates info string", "\n```foo`bar\n## Output\n", true}, {"closing fence with info does not close block", "\n```md\n```x\n## Output\n```\n", false}, {"case insensitive heading", "\n## wOrKfLoW\n", true}} {
		t.Run(tc.name, func(t *testing.T) {
			root := fixture(t)
			p := addSkill(t, root, "example", "example")
			appendText(t, p, tc.markdown)
			if got := codeSet(t, root)["english-control-heading"]; got != tc.finding {
				t.Fatalf("heading finding %v want %v", got, tc.finding)
			}
		})
	}
}
func TestReadmeNoticeAndDependenciesAreExcludedFromLanguageCheck(t *testing.T) {
	root := fixture(t)
	p := addSkill(t, root, "example", "example")
	for _, relative := range []string{"README.md", "NOTICE.md", "node_modules/dependency/guide.md"} {
		write(t, filepath.Join(filepath.Dir(p), relative), "# Workflow\n")
	}
	if codeSet(t, root)["english-control-heading"] {
		t.Fatal("excluded heading was checked")
	}
}
func TestIgnoredDeploymentCopiesAreNotInventoried(t *testing.T) {
	root := fixture(t)
	addSkill(t, root, "example", "example")
	write(t, filepath.Join(root, ".agents/skills/example/SKILL.md"), "not a source skill\n")
	skills, f, e := check(root)
	if e != nil || len(skills) != 1 || len(f) != 0 {
		t.Fatal(skills, f, e)
	}
}
func TestCLIJSONAndExitStatus(t *testing.T) {
	root := fixture(t)
	p := addSkill(t, root, "example", "example")
	var stdout, stderr bytes.Buffer
	if code := run([]string{"--root", root, "--json"}, &stdout, &stderr); code != 0 {
		t.Fatal(code, stderr.String())
	}
	var report struct {
		Skills   int       `json:"skills"`
		Findings []finding `json:"findings"`
	}
	if e := json.Unmarshal(stdout.Bytes(), &report); e != nil || report.Skills != 1 || len(report.Findings) != 0 {
		t.Fatal(e, stdout.String())
	}
	appendText(t, p, "\n## Workflow\n")
	stdout.Reset()
	if code := run([]string{"--root", root}, &stdout, &stderr); code != 1 || !strings.Contains(stdout.String(), "[english-control-heading]") {
		t.Fatal(code, stdout.String())
	}
}

func TestInvalidUTF8MarkdownCannotPassInventory(t *testing.T) {
	root := fixture(t)
	path := addSkill(t, root, "example", "example")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(path, append(data, 255), 0644); err != nil {
		t.Fatal(err)
	}
	var stdout, stderr bytes.Buffer
	if code := run([]string{"--root", root, "--json"}, &stdout, &stderr); code != 1 {
		t.Fatal(code, stdout.String())
	}
}

func TestOmittedRootUsesSourceCheckoutInsteadOfCallerDirectory(t *testing.T) {
	cwd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	expected, _, err := check(filepath.Join(cwd, "../.."))
	if err != nil || len(expected) == 0 {
		t.Fatal(err, expected)
	}
	t.Chdir(t.TempDir())
	var stdout, stderr bytes.Buffer
	code := run([]string{"--json"}, &stdout, &stderr)
	var report struct {
		Skills int `json:"skills"`
	}
	if err := json.Unmarshal(stdout.Bytes(), &report); err != nil {
		t.Fatal(err, stdout.String(), stderr.String())
	}
	if code != 0 || report.Skills != len(expected) {
		t.Fatal(code, report.Skills, len(expected), stderr.String())
	}
}
