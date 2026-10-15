package main

import (
	"encoding/json"
	"os"

	review "github.com/nananaman/skills/plugin/skills/review-diff-code"
)

func main() {
	cwd, err := os.Getwd()
	if err != nil {
		_ = json.NewEncoder(os.Stderr).Encode(map[string]any{"error": map[string]string{"code": "internal_error", "message": err.Error()}})
		os.Exit(2)
	}
	os.Exit(review.Run(os.Args[1:], cwd, os.Stdout, os.Stderr))
}
