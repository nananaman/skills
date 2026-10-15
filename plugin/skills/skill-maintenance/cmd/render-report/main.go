// render-report turns sanitized daily JSON into fixed offline HTML and Markdown.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"github.com/nananaman/skills/plugin/skills/skill-maintenance/internal/maintenance"
	"os"
)

func run() int {
	flags := flag.NewFlagSet("render-report", flag.ContinueOnError)
	var input, repo, output string
	flags.StringVar(&input, "input", "", "sanitized report JSON, never source logs or state")
	flags.StringVar(&repo, "repo", "", "improvement repository, not an output destination")
	flags.StringVar(&output, "output", "", "new private directory outside Git")
	if err := flags.Parse(os.Args[1:]); err != nil {
		if err == flag.ErrHelp {
			return 0
		}
		return 2
	}
	if flags.NArg() != 0 || input == "" || repo == "" || output == "" {
		fmt.Fprintln(os.Stderr, "--input, --repo and --output are required; no positional arguments")
		return 2
	}
	result, err := maintenance.RenderFile(input, repo, output)
	if err != nil {
		fmt.Fprintf(os.Stderr, "render failed: %v\n", err)
		return 1
	}
	if err := json.NewEncoder(os.Stdout).Encode(result); err != nil {
		fmt.Fprintf(os.Stderr, "render failed: %v\n", err)
		return 1
	}
	return 0
}
func main() { os.Exit(run()) }
