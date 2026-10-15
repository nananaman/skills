package distribution_test

import (
	"context"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

// Distribution uses the same sources for a complete plugin and an isolated APM
// skill. Builds go outside both copies so the audit never sees generated files.
func TestPluginAndStandaloneSkillsBuildAndStartOnMac(t *testing.T) {
	repo, err := filepath.Abs("..")
	if err != nil {
		t.Fatal(err)
	}
	commands := []struct{ skill, command string }{{"apm-usage", "check-apm-deployment"}, {"review-diff-code", "review-diff-code"}, {"skill-maintenance", "session-reader"}, {"skill-maintenance", "render-report"}, {"skill-workbench", "workbench"}}
	for _, mode := range []string{"plugin", "standalone"} {
		t.Run(mode, func(t *testing.T) {
			root := t.TempDir()
			// APM may deploy a skill inside a consumer's unrelated Go workspace.
			consumer := filepath.Join(root, "consumer")
			if err := os.Mkdir(consumer, 0755); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(filepath.Join(consumer, "go.mod"), []byte("module example.invalid/consumer\n\ngo 1.27.0\n"), 0644); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(filepath.Join(root, "go.work"), []byte("go 1.27.0\n\nuse ./consumer\n"), 0644); err != nil {
				t.Fatal(err)
			}
			plugin := filepath.Join(root, "配布 plugin")
			if mode == "plugin" {
				copyDirectory(t, filepath.Join(repo, "plugin"), plugin)
			}
			for _, item := range commands {
				t.Run(item.command, func(t *testing.T) {
					skill := filepath.Join(plugin, "skills", item.skill)
					if mode == "standalone" {
						skill = filepath.Join(root, "単体 skill", item.skill)
						if _, err := os.Stat(skill); os.IsNotExist(err) {
							copyDirectory(t, filepath.Join(repo, "plugin/skills", item.skill), skill)
						}
					}
					output := filepath.Join(root, "binary", item.command)
					if err := os.MkdirAll(filepath.Dir(output), 0755); err != nil {
						t.Fatal(err)
					}
					run(t, root, "go", "-C", skill, "build", "-mod=readonly", "-o", output, "./cmd/"+item.command)
					run(t, root, output, "--help")
				})
			}
		})
	}
}
func run(t *testing.T, cwd, name string, args ...string) {
	t.Helper()
	ctx, cancel := context.WithTimeout(t.Context(), 2*time.Minute)
	defer cancel()
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Dir = cwd
	cmd.Env = append(os.Environ(), "GOWORK=off")
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("%s %v: %v\n%s", name, args, err, out)
	}
}
func copyDirectory(t *testing.T, source, destination string) {
	t.Helper()
	err := filepath.WalkDir(source, func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() && entry.Name() == "__pycache__" {
			return filepath.SkipDir
		}
		if filepath.Ext(path) == ".pyc" {
			return nil
		}
		relative, err := filepath.Rel(source, path)
		if err != nil {
			return err
		}
		target := filepath.Join(destination, relative)
		if entry.IsDir() {
			return os.MkdirAll(target, 0755)
		}
		content, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		return os.WriteFile(target, content, info.Mode().Perm())
	})
	if err != nil {
		t.Fatal(err)
	}
}
