// session-reader exports explicitly authorized completed local Codex sessions.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"github.com/nananaman/skills/plugin/skills/skill-maintenance/internal/maintenance"
	"os"
	"path/filepath"
)

func run() int {
	flags := flag.NewFlagSet("session-reader", flag.ContinueOnError)
	var options maintenance.CollectOptions
	var source string
	flags.StringVar(&options.Sessions, "sessions", "", "explicitly authorized file or directory")
	flags.StringVar(&options.Output, "output", "", "new private directory outside Git")
	flags.StringVar(&options.Repo, "repo", "", "improvement repository, never a history scope grant")
	flags.StringVar(&source, "source", "", "caller source.json scope annotations and excluded roots")
	flags.StringVar(&options.Since, "since", "", "inclusive activity timestamp with timezone")
	flags.StringVar(&options.Until, "until", "", "exclusive activity timestamp with timezone")
	if err := flags.Parse(os.Args[1:]); err != nil {
		if err == flag.ErrHelp {
			return 0
		}
		return 2
	}
	if flags.NArg() != 0 || options.Sessions == "" || options.Output == "" || options.Repo == "" {
		fmt.Fprintln(os.Stderr, "--sessions, --output and --repo are required; no positional arguments")
		return 2
	}
	if source != "" {
		data, err := os.ReadFile(source)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
		if err := json.Unmarshal(data, &options.Source); err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
		if options.Source == nil {
			fmt.Fprintln(os.Stderr, "source must be a JSON object")
			return 1
		}
	}
	result, err := maintenance.Collect(options)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	if err := json.NewEncoder(os.Stdout).Encode(maintenance.Object{"counts": result["counts"], "elapsed_seconds": result["elapsed_seconds"], "manifest": filepath.Join(options.Output, "manifest.json")}); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	counts := result["counts"].(map[string]int)
	if counts["failed"]+counts["partial"]+counts["held"] > 0 {
		return 1
	}
	return 0
}
func main() { os.Exit(run()) }
