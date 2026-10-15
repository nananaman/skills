package maintenance

import (
	"bufio"
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"reflect"
	"regexp"
	"sort"
	"strings"
	"time"
	"unicode/utf8"
)

type Object = map[string]any

var sourceGap = regexp.MustCompile(`(?i)output (?:was )?truncated|(?:tokens|characters) truncated|omitted \d+ lines`)
var errInvalidSourceUTF8 = errors.New("invalid UTF-8 in source")

type Version struct {
	Size     int64
	Modified int64
}
type ReadResult struct {
	Metadata      Object   `json:"metadata"`
	Items         []Object `json:"items"`
	Visible       int      `json:"visible_items"`
	Errors        []Object `json:"errors"`
	Activity      bool     `json:"-"`
	TimestampSeen bool     `json:"-"`
	Version       Version  `json:"-"`
	Gaps          []int    `json:"source_gaps"`
	Changed       bool     `json:"changed_during_read"`
	Lifecycle     []Object `json:"lifecycle"`
}

func instant(value string) (time.Time, error) {
	for _, layout := range []string{time.RFC3339Nano, "2006-01-02 15:04:05.999999999Z07:00", "2006-01-02T15:04:05.999999999-0700", "2006-01-02T15:04Z07:00"} {
		if moment, err := time.Parse(layout, value); err == nil {
			return moment, nil
		}
	}
	return time.Time{}, errors.New("timestamp needs a valid ISO time with timezone")
}
func fileVersion(info os.FileInfo) Version { return Version{info.Size(), info.ModTime().UnixNano()} }
func str(value any) string                 { s, _ := value.(string); return s }
func truth(value any) bool {
	switch v := value.(type) {
	case nil:
		return false
	case string:
		return v != ""
	case bool:
		return v
	case float64:
		return v != 0
	case json.Number:
		n, err := v.Float64()
		return err != nil || n != 0
	case []any:
		return len(v) > 0
	case map[string]any:
		return len(v) > 0
	default:
		return true
	}
}
func sameVersion(path string, v Version) bool {
	info, err := os.Stat(path)
	return err == nil && fileVersion(info) == v
}

// ReadSession streams one JSONL item at a time, bounded to the indexed byte end.
// A nil sink collects items for callers inspecting a single authorized file.
func ReadSession(path string, lower, upper *time.Time, indexOnly bool, sink io.Writer, endBytes *int64) (ReadResult, error) {
	result := ReadResult{Metadata: Object{}, Items: []Object{}, Errors: []Object{}, Gaps: []int{}, Lifecycle: []Object{}}
	before, err := os.Stat(path)
	if err != nil {
		return result, err
	}
	result.Version = fileVersion(before)
	end := before.Size()
	if endBytes != nil {
		end = *endBytes
	}
	f, err := openSource(path)
	if err != nil {
		return result, err
	}
	defer f.Close()
	reader := bufio.NewReader(io.LimitReader(f, end))
	encoder := json.NewEncoder(sink)
	encoder.SetEscapeHTML(false)
	for lineNumber := 1; ; lineNumber++ {
		line, readErr := reader.ReadBytes('\n')
		if len(line) == 0 && readErr == io.EOF {
			break
		}
		if readErr != nil && readErr != io.EOF {
			return result, readErr
		}
		var record Object
		failure := ""
		if !utf8.Valid(line) {
			failure = errorKind(errInvalidSourceUTF8)
		} else {
			var value, trailing any
			decoder := json.NewDecoder(bytes.NewReader(line))
			decoder.UseNumber()
			if err := decoder.Decode(&value); err != nil {
				failure = "JSONDecodeError"
			} else if err := decoder.Decode(&trailing); err != io.EOF {
				failure = "JSONDecodeError"
			} else {
				var valid bool
				record, valid = value.(map[string]any)
				if !valid {
					failure = "AttributeError"
				}
			}
		}
		if failure != "" {
			result.Errors = append(result.Errors, Object{"line": lineNumber, "error": failure})
			result.Lifecycle = append(result.Lifecycle, Object{"line": lineNumber, "timestamp": nil, "event": "unknown"})
			continue
		}
		payload := Object{}
		if p, ok := record["payload"]; ok {
			var valid bool
			payload, valid = p.(map[string]any)
			if !valid {
				result.Errors = append(result.Errors, Object{"line": lineNumber, "error": "AttributeError"})
				result.Lifecycle = append(result.Lifecycle, Object{"line": lineNumber, "timestamp": nil, "event": "unknown"})
				continue
			}
		}
		stamp := record["timestamp"]
		if truth(stamp) {
			moment, err := instant(str(stamp))
			if err != nil {
				kind := "ValueError"
				if _, ok := stamp.(string); !ok {
					kind = "AttributeError"
				}
				result.Errors = append(result.Errors, Object{"line": lineNumber, "error": kind})
				result.Lifecycle = append(result.Lifecycle, Object{"line": lineNumber, "timestamp": nil, "event": "unknown"})
				continue
			}
			result.TimestampSeen = true
			result.Activity = result.Activity || ((lower == nil || !moment.Before(*lower)) && (upper == nil || moment.Before(*upper)))
			if upper != nil && !moment.Before(*upper) {
				continue
			}
		}
		if record["type"] == "session_meta" {
			result.Metadata = Object{}
			for _, key := range []string{"id", "cwd", "source", "parent_thread_id"} {
				result.Metadata[key] = payload[key]
			}
		}
		if record["type"] == "event_msg" && (payload["type"] == "task_started" || payload["type"] == "task_complete" || payload["type"] == "turn_aborted") {
			result.Lifecycle = append(result.Lifecycle, Object{"line": lineNumber, "timestamp": stamp, "event": payload["type"]})
		}
		if indexOnly || record["type"] != "response_item" || payload["type"] == "reasoning" || payload["phase"] == "analysis" {
			continue
		}
		if upper != nil && !truth(stamp) {
			result.Errors = append(result.Errors, Object{"line": lineNumber, "error": "missing item timestamp; withheld at cutoff"})
			continue
		}
		clean := Object{}
		for key, value := range payload {
			if key != "encrypted_content" {
				clean[key] = value
			}
		}
		item := Object{"line": lineNumber, "timestamp": stamp, "payload": clean}
		if sink == nil {
			result.Items = append(result.Items, item)
		} else if err := encoder.Encode(item); err != nil {
			return result, err
		}
		result.Visible++
		if strings.HasSuffix(str(clean["type"]), "_output") {
			data, _ := json.Marshal(clean)
			if sourceGap.Match(data) {
				result.Gaps = append(result.Gaps, lineNumber)
			}
		}
	}
	after, err := os.Stat(path)
	if err != nil {
		return result, err
	}
	result.Changed = result.Version != fileVersion(after)
	return result, nil
}
func contains(values any, target any) bool {
	list, _ := values.([]any)
	for _, value := range list {
		if reflect.DeepEqual(value, target) {
			return true
		}
	}
	return false
}
func ScopeReason(path string, source Object) (Object, string, error) {
	f, err := openSource(path)
	if err != nil {
		return nil, "", err
	}
	defer f.Close()
	line, err := bufio.NewReader(f).ReadBytes('\n')
	if err != nil && err != io.EOF {
		return nil, "", err
	}
	if !utf8.Valid(line) {
		return nil, "", errInvalidSourceUTF8
	}
	var record Object
	if err := json.Unmarshal(line, &record); err != nil {
		return nil, "", err
	}
	if record["type"] != "session_meta" {
		return nil, "", errors.New("session metadata missing")
	}
	metadata, ok := record["payload"].(map[string]any)
	if !ok {
		return nil, "", errors.New("session metadata missing")
	}
	if contains(source["exclude_roots"], metadata["id"]) {
		return nil, "caller-excluded root", nil
	}
	_, child := metadata["source"].(map[string]any)
	if truth(metadata["parent_thread_id"]) || child {
		return nil, "child session; correlate with parent, not independent evidence", nil
	}
	all := source["repository_scope"] == "all"
	if all && !contains(source["development_roots"], metadata["id"]) {
		return nil, "development task classification required from caller", nil
	}
	git, _ := metadata["git"].(map[string]any)
	remote := str(git["repository_url"])
	slug := ""
	if strings.HasPrefix(remote, "git@github.com:") {
		slug = strings.TrimSuffix(strings.TrimPrefix(remote, "git@github.com:"), ".git")
	}
	if strings.HasPrefix(remote, "https://github.com/") {
		u, err := url.Parse(remote)
		if err == nil && u.RawQuery == "" && u.Fragment == "" {
			slug = strings.TrimSuffix(strings.Trim(u.EscapedPath(), "/"), ".git")
		}
	}
	repos, _ := source["repos"].([]any)
	for _, value := range repos {
		repository, ok := value.(map[string]any)
		if !ok {
			return nil, "", errors.New("invalid source repository")
		}
		if slug != "" && slug == str(repository["id"]) {
			return repository, "", nil
		}
		if (!all || remote == "") && truth(metadata["cwd"]) && truth(repository["cwd"]) {
			cwd, e1 := canonical(str(metadata["cwd"]))
			registered, e2 := canonical(str(repository["cwd"]))
			if e1 == nil && e2 == nil && cwd == registered {
				return repository, "", nil
			}
		}
	}
	if all {
		for _, key := range []string{"repository_url", "commit_hash", "branch"} {
			if strings.TrimSpace(str(git[key])) != "" {
				var id any
				if slug != "" {
					id = slug
				}
				return Object{"id": id, "information_scope": nil}, "", nil
			}
		}
		return nil, "repository context unknown; caller classification required", nil
	}
	return nil, "outside configured source repositories or unresolved ownership", nil
}

type CollectOptions struct {
	Sessions, Output, Repo, Since, Until string
	Source                               Object
}
type ReadFunc func(string, *time.Time, *time.Time, bool, io.Writer, *int64) (ReadResult, error)

func Collect(options CollectOptions) (Object, error) { return collect(options, ReadSession) }
func collect(options CollectOptions, read ReadFunc) (Object, error) {
	start := time.Now()
	source := options.Source
	if source != nil {
		scope := source["repository_scope"]
		if scope != nil && scope != "listed" && scope != "all" {
			return nil, errors.New("repository_scope must be listed or all")
		}
		if scope == "all" {
			roots, ok := source["development_roots"].([]any)
			if !ok {
				return nil, errors.New("all requires development_roots classified by caller")
			}
			for _, root := range roots {
				value, ok := root.(string)
				if !ok || strings.TrimSpace(value) == "" {
					return nil, errors.New("all requires development_roots classified by caller")
				}
			}
		}
	}
	var lower, upper *time.Time
	for _, bound := range []struct {
		value string
		dest  **time.Time
	}{{options.Since, &lower}, {options.Until, &upper}} {
		if bound.value != "" {
			moment, err := instant(bound.value)
			if err != nil {
				return nil, err
			}
			*bound.dest = &moment
		}
	}
	if lower != nil && upper != nil && !lower.Before(*upper) {
		return nil, errors.New("since must precede until")
	}
	sessions, err := filepath.Abs(options.Sessions)
	if err != nil {
		return nil, err
	}
	for component := sessions; ; component = filepath.Dir(component) {
		info, err := os.Lstat(component)
		if err != nil {
			return nil, err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return nil, errors.New("authorized source path must have no symlink components; use its canonical path")
		}
		if filepath.Dir(component) == component {
			break
		}
	}
	info, err := os.Stat(sessions)
	if err != nil {
		return nil, err
	}
	paths := []string{sessions}
	if info.IsDir() {
		paths = []string{}
		err = filepath.WalkDir(sessions, func(path string, entry os.DirEntry, err error) error {
			if err != nil {
				return err
			}
			if !entry.IsDir() && strings.HasSuffix(entry.Name(), ".jsonl") {
				paths = append(paths, path)
			}
			return nil
		})
		if err != nil {
			return nil, err
		}
		sort.Strings(paths)
	}
	if err := PrivateDirectory(options.Output, options.Repo); err != nil {
		return nil, err
	}
	counts := map[string]int{"discovered": len(paths), "selected": 0, "read": 0, "partial": 0, "failed": 0, "outside_period": 0, "excluded": 0, "held": 0}
	entries := []Object{}
	for number, path := range paths {
		entry := Object{"source": path, "status": "failed"}
		itemStart := time.Now()
		transcript := filepath.Join(options.Output, fmt.Sprintf("session-%05d.jsonl", number+1))
		selected := false
		process := func() error {
			candidate, err := os.Lstat(path)
			if err != nil {
				return err
			}
			if !candidate.Mode().IsRegular() || candidate.Mode()&os.ModeSymlink != 0 {
				return errors.New("candidate is not a regular file within authorized directory")
			}
			resolved, err := filepath.EvalSymlinks(path)
			if err != nil {
				return err
			}
			if info.IsDir() && !within(resolved, sessions) {
				return errors.New("candidate is not a regular file within authorized directory")
			}
			if source != nil {
				scope, reason, err := ScopeReason(path, source)
				if err != nil {
					return err
				}
				if reason != "" {
					entry["status"] = "excluded"
					entry["reason"] = reason
					return nil
				}
				entry["repository"] = scope["id"]
				entry["information_scope"] = scope["information_scope"]
			}
			index, err := read(path, lower, upper, true, nil, nil)
			if err != nil {
				return err
			}
			entry["metadata"] = index.Metadata
			if (lower != nil || upper != nil) && index.TimestampSeen && !index.Activity {
				entry["status"] = "outside_period"
				entry["reason"] = "no activity in requested period"
				return nil
			}
			selected = true
			if !sameVersion(path, index.Version) {
				entry["status"] = "held"
				entry["reason"] = "session changed after index; visible body not exported"
				return nil
			}
			if !truth(index.Metadata["id"]) {
				entry["reason"] = "metadata missing"
				return nil
			}
			if len(index.Lifecycle) == 0 || index.Lifecycle[len(index.Lifecycle)-1]["event"] == "unknown" {
				entry["status"] = "held"
				entry["reason"] = "termination unknown; visible body not exported"
				return nil
			}
			if index.Changed || index.Lifecycle[len(index.Lifecycle)-1]["event"] == "task_started" {
				entry["status"] = "held"
				entry["reason"] = "active or changing session; visible body not exported"
				return nil
			}
			f, err := createPrivate(transcript)
			if err != nil {
				return err
			}
			data, err := read(path, lower, upper, false, f, &index.Version.Size)
			closeErr := f.Close()
			if err != nil {
				return err
			}
			if closeErr != nil {
				return closeErr
			}
			entry["metadata"] = data.Metadata
			entry["visible_items"] = data.Visible
			entry["errors"] = data.Errors
			entry["source_gaps"] = data.Gaps
			entry["changed_during_read"] = data.Changed
			entry["lifecycle"] = data.Lifecycle
			if data.Changed || !sameVersion(path, index.Version) || (len(data.Lifecycle) > 0 && data.Lifecycle[len(data.Lifecycle)-1]["event"] == "task_started") {
				entry["status"] = "held"
				entry["reason"] = "session changed or became active before export"
			} else if !truth(data.Metadata["id"]) || data.Visible == 0 {
				entry["reason"] = "metadata or visible context missing"
			} else {
				entry["status"] = "read"
				if len(data.Errors) > 0 || len(data.Gaps) > 0 || ((lower != nil || upper != nil) && !data.TimestampSeen) {
					entry["status"] = "partial"
				}
				entry["transcript"] = transcript
			}
			return nil
		}
		if err := process(); err != nil {
			selected = true
			entry["reason"] = errorKind(err)
		}
		if entry["transcript"] == nil {
			if err := os.Remove(transcript); err != nil && !errors.Is(err, os.ErrNotExist) {
				return nil, err
			}
		}
		if selected {
			counts["selected"]++
		}
		counts[str(entry["status"])]++
		entry["elapsed_seconds"] = time.Since(itemStart).Seconds()
		entries = append(entries, entry)
	}
	var since, until any
	if options.Since != "" {
		since = options.Since
	}
	if options.Until != "" {
		until = options.Until
	}
	result := Object{"counts": counts, "period": Object{"since": since, "until": until}, "sessions": entries, "elapsed_seconds": time.Since(start).Seconds()}
	if err := writeJSON(filepath.Join(options.Output, "manifest.json"), result); err != nil {
		return nil, err
	}
	return result, nil
}
func errorKind(err error) string {
	if errors.Is(err, errInvalidSourceUTF8) {
		return "UnicodeDecodeError"
	}
	var syntax *json.SyntaxError
	if errors.As(err, &syntax) {
		return "JSONDecodeError"
	}
	var path *os.PathError
	if errors.As(err, &path) {
		return "OSError"
	}
	return "ValueError"
}
