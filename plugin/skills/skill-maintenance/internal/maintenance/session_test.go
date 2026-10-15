package maintenance

import (
	"bytes"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func testRoot(t *testing.T) string {
	t.Helper()
	root, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	return root
}
func writeRecords(t *testing.T, path string, records []Object) {
	t.Helper()
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	encoder := json.NewEncoder(f)
	for _, record := range records {
		if err := encoder.Encode(record); err != nil {
			t.Fatal(err)
		}
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
}
func completed(id string) []Object {
	return []Object{{"type": "session_meta", "payload": Object{"id": id}}, {"type": "response_item", "payload": Object{"type": "message", "role": "user", "content": []any{Object{"type": "text", "text": "Development request"}}}}, {"type": "event_msg", "payload": Object{"type": "task_complete"}}}
}
func options(root, source string) CollectOptions {
	return CollectOptions{Sessions: source, Output: filepath.Join(root, "private"), Repo: filepath.Join(root, "repo")}
}
func counts(result Object) map[string]int { return result["counts"].(map[string]int) }
func entries(result Object) []Object      { return result["sessions"].([]Object) }
func collectOK(t *testing.T, o CollectOptions) Object {
	t.Helper()
	result, err := Collect(o)
	if err != nil {
		t.Fatal(err)
	}
	return result
}
func TestVisibleContextPreservesCallsResultsAndOrderWithoutReasoning(t *testing.T) {
	root := testRoot(t)
	path := filepath.Join(root, "session.jsonl")
	records := []Object{{"type": "session_meta", "payload": Object{"id": "test", "cwd": "/example"}}, {"type": "response_item", "payload": Object{"type": "message", "content": []any{"Keep fixture assertions."}, "encrypted_content": "opaque-private"}}, {"type": "response_item", "payload": Object{"type": "custom_tool_call", "input": "test --env-disabled"}}, {"type": "response_item", "payload": Object{"type": "custom_tool_call_output", "output": strings.Repeat("ordinary context\n", 1000)}}, {"type": "response_item", "payload": Object{"type": "reasoning", "summary": "private"}}, {"type": "response_item", "payload": Object{"type": "message", "phase": "analysis", "content": "private"}}, {"type": "response_item", "payload": Object{"type": "message", "phase": "final_answer", "content": "Done."}}}
	writeRecords(t, path, records)
	result, err := ReadSession(path, nil, nil, false, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	want := []int{2, 3, 4, 7}
	if len(result.Items) != len(want) {
		t.Fatal(result.Items)
	}
	for i, line := range want {
		if result.Items[i]["line"] != line {
			t.Fatal(result.Items)
		}
	}
	data, _ := json.Marshal(result.Items)
	if bytes.Contains(data, []byte("private")) || !bytes.Contains(data, []byte("test --env-disabled")) {
		t.Fatal(string(data))
	}
}
func TestCollectionAccountsForEveryFileAndIsolatesCorruptHistory(t *testing.T) {
	root := testRoot(t)
	source := filepath.Join(root, "sessions")
	os.Mkdir(source, 0700)
	for _, id := range []string{"a", "b", "c"} {
		writeRecords(t, filepath.Join(source, id+".jsonl"), completed(id))
	}
	os.WriteFile(filepath.Join(source, "broken.jsonl"), []byte("{invalid\n"), 0600)
	result := collectOK(t, options(root, source))
	for key, want := range map[string]int{"discovered": 4, "selected": 4, "read": 3, "failed": 1, "partial": 0, "outside_period": 0, "excluded": 0, "held": 0} {
		if counts(result)[key] != want {
			t.Fatalf("%s: %v", key, counts(result))
		}
	}
	if len(entries(result)) != 4 {
		t.Fatal(result)
	}
}
func TestPeriodSelectionRetainsEarlierContextAndMarksSourceGaps(t *testing.T) {
	root := testRoot(t)
	path := filepath.Join(root, "session.jsonl")
	records := completed("test")
	records[1]["timestamp"] = "2026-10-01T01:00:00Z"
	records = append(records[:2], Object{"timestamp": "2026-10-07T01:00:00Z", "type": "response_item", "payload": Object{"type": "function_call_output", "output": "Output truncated by source"}}, Object{"timestamp": "2026-10-07T01:01:00Z", "type": "event_msg", "payload": Object{"type": "task_complete"}}, Object{"timestamp": "2026-10-08T00:00:00Z", "type": "response_item", "payload": Object{"type": "message", "content": "Future private request"}})
	writeRecords(t, path, records)
	o := options(root, path)
	o.Since = "2026-10-07T00:00:00Z"
	o.Until = "2026-10-08T00:00:00Z"
	entry := entries(collectOK(t, o))[0]
	data, err := os.ReadFile(str(entry["transcript"]))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(data, []byte("Development request")) || !bytes.Contains(data, []byte("Output truncated")) || bytes.Contains(data, []byte("Future")) {
		t.Fatal(string(data))
	}
	if entry["status"] != "partial" || entry["source_gaps"].([]int)[0] != 3 {
		t.Fatal(entry)
	}
}
func TestSourceScopeExcludesOtherRepositoriesAndChildrenBeforeBodyRead(t *testing.T) {
	root := testRoot(t)
	source := filepath.Join(root, "sessions")
	os.Mkdir(source, 0700)
	for _, item := range []struct{ id, remote, parent string }{{"allowed", "example/app", ""}, {"other", "another/private", ""}, {"child", "example/app", "allowed"}} {
		records := completed(item.id)
		records[0]["payload"] = Object{"id": item.id, "parent_thread_id": item.parent, "git": Object{"repository_url": "https://github.com/" + item.remote + ".git"}}
		path := filepath.Join(source, item.id+".jsonl")
		writeRecords(t, path, records)
		if item.id != "allowed" {
			f, _ := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0)
			f.WriteString("{unread corrupt body\n")
			f.Close()
		}
	}
	o := options(root, source)
	o.Source = Object{"repos": []any{Object{"id": "example/app"}}}
	result := collectOK(t, o)
	if counts(result)["read"] != 1 || counts(result)["excluded"] != 2 || counts(result)["failed"] != 0 {
		t.Fatal(result)
	}
}
func TestAllRepositoriesPreservesKnownScopesWithoutReusingCwdAcrossRemotes(t *testing.T) {
	cases := []struct {
		name       string
		git        any
		scope      any
		repository any
	}{{"listed", Object{"repository_url": "https://github.com/example/app.git"}, "personal:example", "example/app"}, {"new", Object{"repository_url": "https://github.com/example/new.git"}, nil, "example/new"}, {"other-host", Object{"repository_url": "https://gitlab.example/team/app.git"}, nil, nil}, {"local", Object{"commit_hash": strings.Repeat("a", 40)}, "personal:example", "example/app"}, {"missing", nil, "personal:example", "example/app"}, {"different", Object{"repository_url": "https://github.com/other/private.git"}, nil, "other/private"}}
	root := testRoot(t)
	source := filepath.Join(root, "sessions")
	os.Mkdir(source, 0700)
	roots := []any{}
	for _, item := range cases {
		records := completed(item.name)
		records[0]["payload"] = Object{"id": item.name, "cwd": filepath.Join(root, "registered"), "git": item.git}
		writeRecords(t, filepath.Join(source, item.name+".jsonl"), records)
		roots = append(roots, item.name)
	}
	o := options(root, source)
	o.Source = Object{"repository_scope": "all", "development_roots": roots, "repos": []any{Object{"id": "example/app", "cwd": filepath.Join(root, "registered"), "information_scope": "personal:example"}}}
	result := collectOK(t, o)
	if counts(result)["read"] != len(cases) {
		t.Fatal(result)
	}
	for _, entry := range entries(result) {
		id := str(entry["metadata"].(Object)["id"])
		for _, item := range cases {
			if id == item.name && (entry["information_scope"] != item.scope || entry["repository"] != item.repository) {
				t.Fatalf("%s: %v", id, entry)
			}
		}
	}
}
func TestAllRepositoriesExcludesUnclassifiedUnknownChildrenAndCallerExclusions(t *testing.T) {
	root := testRoot(t)
	source := filepath.Join(root, "sessions")
	os.Mkdir(source, 0700)
	for _, item := range []struct {
		id     string
		git    Object
		parent string
	}{{"non-development", Object{"repository_url": "https://github.com/example/app.git"}, ""}, {"empty-git", Object{}, ""}, {"unknown-git", Object{"unrecognized": "value"}, ""}, {"child", Object{"repository_url": "https://github.com/example/app.git"}, "parent"}, {"maintenance", Object{"commit_hash": "a"}, ""}} {
		data, _ := json.Marshal(Object{"type": "session_meta", "payload": Object{"id": item.id, "git": item.git, "parent_thread_id": item.parent}})
		os.WriteFile(filepath.Join(source, item.id+".jsonl"), append(data, []byte("\n{unread corrupt body\n")...), 0600)
	}
	o := options(root, source)
	o.Source = Object{"repository_scope": "all", "development_roots": []any{"empty-git", "unknown-git", "child", "maintenance"}, "exclude_roots": []any{"maintenance"}}
	result := collectOK(t, o)
	if counts(result)["excluded"] != 5 || counts(result)["failed"] != 0 {
		t.Fatal(result)
	}
}
func TestInvalidScopeAndDevelopmentRootsFailBeforeCreatingOutput(t *testing.T) {
	for _, source := range []Object{{"repository_scope": "*"}, {"repository_scope": "all"}, {"repository_scope": "all", "development_roots": "*"}, {"repository_scope": "all", "development_roots": []any{7}}, {"repository_scope": "all", "development_roots": []any{" "}}} {
		root := testRoot(t)
		o := options(root, root)
		o.Source = source
		if _, err := Collect(o); err == nil {
			t.Fatal(source)
		}
		if _, err := os.Stat(o.Output); !os.IsNotExist(err) {
			t.Fatal(err)
		}
	}
}
func TestActiveUnknownAndCorruptTerminationAreHeldWithoutExport(t *testing.T) {
	for _, last := range []string{"task_started", "", "invalid"} {
		t.Run(last, func(t *testing.T) {
			root := testRoot(t)
			path := filepath.Join(root, "active.jsonl")
			records := completed("active")
			if last == "" || last == "invalid" {
				records = records[:2]
			} else {
				records[2]["payload"] = Object{"type": last}
			}
			writeRecords(t, path, records)
			if last == "invalid" {
				f, _ := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0)
				f.WriteString("{invalid\n")
				f.Close()
			}
			o := options(root, path)
			entry := entries(collectOK(t, o))[0]
			if entry["status"] != "held" {
				t.Fatal(entry)
			}
			paths, _ := filepath.Glob(filepath.Join(o.Output, "session-*"))
			if len(paths) != 0 {
				t.Fatal(paths)
			}
			data, _ := os.ReadFile(filepath.Join(o.Output, "manifest.json"))
			if bytes.Contains(data, []byte("Development request")) {
				t.Fatal(string(data))
			}
		})
	}
}
func TestSymlinkCandidateDoesNotExpandAuthorizedDirectory(t *testing.T) {
	root := testRoot(t)
	source := filepath.Join(root, "sessions")
	os.Mkdir(source, 0700)
	outside := filepath.Join(root, "outside.jsonl")
	writeRecords(t, outside, completed("outside"))
	os.Symlink(outside, filepath.Join(source, "link.jsonl"))
	result := collectOK(t, options(root, source))
	if counts(result)["failed"] != 1 {
		t.Fatal(result)
	}
}
func TestSourceRootWithSymlinkParentIsRejected(t *testing.T) {
	root := testRoot(t)
	os.MkdirAll(filepath.Join(root, "outside", "sessions"), 0700)
	os.Symlink(filepath.Join(root, "outside"), filepath.Join(root, "alias"))
	o := options(root, filepath.Join(root, "alias", "sessions"))
	if _, err := Collect(o); err == nil {
		t.Fatal("accepted symlink")
	}
	if _, err := os.Stat(o.Output); !os.IsNotExist(err) {
		t.Fatal(err)
	}
}
func TestPrivateOutputRefusesGitAndPreservesExistingDirectory(t *testing.T) {
	root := testRoot(t)
	repo := filepath.Join(root, "repo")
	os.MkdirAll(filepath.Join(repo, ".git"), 0700)
	for _, path := range []string{filepath.Join(repo, "private"), filepath.Join(repo, ".git", "private")} {
		if err := PrivateDirectory(path, repo); err == nil {
			t.Fatal(path)
		}
	}
	other := filepath.Join(root, "other")
	os.MkdirAll(filepath.Join(other, ".git"), 0700)
	if err := PrivateDirectory(filepath.Join(other, "private"), repo); err == nil {
		t.Fatal("accepted other checkout")
	}
	output := filepath.Join(root, "private")
	os.Mkdir(output, 0700)
	os.WriteFile(filepath.Join(output, "keep"), []byte("preserve"), 0600)
	if err := PrivateDirectory(output, repo); err == nil {
		t.Fatal("accepted existing")
	}
	data, _ := os.ReadFile(filepath.Join(output, "keep"))
	if string(data) != "preserve" {
		t.Fatal(string(data))
	}
}
func TestIndexByteBoundaryExcludesNewlyAppendedTask(t *testing.T) {
	root := testRoot(t)
	path := filepath.Join(root, "session.jsonl")
	writeRecords(t, path, completed("test"))
	info, _ := os.Stat(path)
	boundary := info.Size()
	f, _ := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0)
	json.NewEncoder(f).Encode(Object{"type": "response_item", "payload": Object{"type": "message", "content": "Appended active task"}})
	f.Close()
	result, err := ReadSession(path, nil, nil, false, nil, &boundary)
	if err != nil {
		t.Fatal(err)
	}
	data, _ := json.Marshal(result.Items)
	if bytes.Contains(data, []byte("Appended active task")) || result.Lifecycle[len(result.Lifecycle)-1]["event"] != "task_complete" {
		t.Fatal(result)
	}
}
func TestAppendAfterIndexDoesNotStartVisibleBodyRead(t *testing.T) {
	root := testRoot(t)
	path := filepath.Join(root, "session.jsonl")
	writeRecords(t, path, completed("test"))
	bodyReads := 0
	read := func(path string, lower, upper *time.Time, index bool, sink io.Writer, end *int64) (ReadResult, error) {
		if sink != nil {
			bodyReads++
		}
		result, err := ReadSession(path, lower, upper, index, sink, end)
		if index {
			f, _ := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0)
			f.WriteString("{\"type\":\"event_msg\",\"payload\":{\"type\":\"task_started\"}}\n")
			f.Close()
		}
		return result, err
	}
	result, err := collect(options(root, path), read)
	if err != nil {
		t.Fatal(err)
	}
	if bodyReads != 0 || counts(result)["held"] != 1 {
		t.Fatal(result, bodyReads)
	}
}
func TestAppendDuringBodyExportRemovesTemporaryTranscript(t *testing.T) {
	root := testRoot(t)
	path := filepath.Join(root, "session.jsonl")
	writeRecords(t, path, completed("test"))
	read := func(path string, lower, upper *time.Time, index bool, sink io.Writer, end *int64) (ReadResult, error) {
		result, err := ReadSession(path, lower, upper, index, sink, end)
		if sink != nil {
			f, _ := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0)
			f.WriteString("{}\n")
			f.Close()
		}
		return result, err
	}
	o := options(root, path)
	result, err := collect(o, read)
	if err != nil {
		t.Fatal(err)
	}
	if counts(result)["held"] != 1 {
		t.Fatal(result)
	}
	paths, _ := filepath.Glob(filepath.Join(o.Output, "session-*"))
	if len(paths) != 0 {
		t.Fatal(paths)
	}
}
func TestCollectionKeepsStreamOrderAndAccountsForOutsidePeriod(t *testing.T) {
	root := testRoot(t)
	source := filepath.Join(root, "sessions")
	os.Mkdir(source, 0700)
	for _, item := range []struct{ id, stamp string }{{"selected", "2026-10-07T01:00:00Z"}, {"old", "2026-10-01T01:00:00Z"}} {
		records := completed(item.id)
		for _, record := range records {
			record["timestamp"] = item.stamp
		}
		writeRecords(t, filepath.Join(source, item.id+".jsonl"), records)
	}
	o := options(root, source)
	o.Since = "2026-10-07T00:00:00Z"
	result := collectOK(t, o)
	if counts(result)["read"] != 1 || counts(result)["outside_period"] != 1 || counts(result)["selected"] != 1 {
		t.Fatal(result)
	}
}
func TestLargeCollectionStreamsPastTotalAndItemSizesWithoutLosingTail(t *testing.T) {
	root := testRoot(t)
	path := filepath.Join(root, "large.jsonl")
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	encoder := json.NewEncoder(f)
	encoder.Encode(Object{"type": "session_meta", "payload": Object{"id": "large"}})
	for n := 0; n < 57; n++ {
		size := 1024 * 1024
		if n == 0 {
			size *= 9
		}
		encoder.Encode(Object{"type": "response_item", "payload": Object{"type": "function_call_output", "output": strings.Repeat("x", size)}})
	}
	encoder.Encode(Object{"type": "response_item", "payload": Object{"type": "function_call_output", "output": "Output truncated by source"}})
	encoder.Encode(Object{"type": "response_item", "payload": Object{"type": "reasoning", "encrypted_content": "opaque-private"}})
	encoder.Encode(Object{"type": "response_item", "payload": Object{"type": "message", "content": "Tail after large outputs"}})
	encoder.Encode(Object{"type": "event_msg", "payload": Object{"type": "task_complete"}})
	f.Close()
	streamed := false
	read := func(path string, l, u *time.Time, index bool, sink io.Writer, end *int64) (ReadResult, error) {
		r, err := ReadSession(path, l, u, index, sink, end)
		if sink != nil {
			streamed = true
			if len(r.Items) != 0 {
				t.Fatal("stream accumulated body")
			}
		}
		return r, err
	}
	o := options(root, path)
	result, err := collect(o, read)
	if err != nil {
		t.Fatal(err)
	}
	entry := entries(result)[0]
	if !streamed || entry["status"] != "partial" || entry["visible_items"] != 59 || entry["source_gaps"].([]int)[0] != 59 {
		t.Fatal(entry)
	}
	transcript, err := os.Open(str(entry["transcript"]))
	if err != nil {
		t.Fatal(err)
	}
	defer transcript.Close()
	decoder := json.NewDecoder(transcript)
	for n := 0; n < 59; n++ {
		var item Object
		if err := decoder.Decode(&item); err != nil {
			t.Fatal(err)
		}
		if n == 58 && item["payload"].(Object)["content"] != "Tail after large outputs" {
			t.Fatal(item)
		}
	}
	var extra Object
	if err := decoder.Decode(&extra); err != io.EOF {
		t.Fatal(err)
	}
}
func TestCutoffWithholdsUntimedVisibleItemsAndMarksPartial(t *testing.T) {
	root := testRoot(t)
	path := filepath.Join(root, "session.jsonl")
	records := completed("test")
	records[2]["timestamp"] = "2026-10-07T01:00:00Z"
	records = append(records[:2], Object{"timestamp": "2026-10-07T00:00:00Z", "type": "response_item", "payload": Object{"type": "message", "content": "Dated context"}}, records[2])
	writeRecords(t, path, records)
	o := options(root, path)
	o.Until = "2026-10-08T00:00:00Z"
	entry := entries(collectOK(t, o))[0]
	if entry["status"] != "partial" || entry["visible_items"] != 1 || len(entry["errors"].([]Object)) != 1 {
		t.Fatal(entry)
	}
}

func TestStreamingPreservesIntegersBeyondFloatPrecision(t *testing.T) {
	root := testRoot(t)
	path := filepath.Join(root, "session.jsonl")
	os.WriteFile(path, []byte("{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"output\":9007199254740993}}\n"), 0600)
	var sink bytes.Buffer
	_, err := ReadSession(path, nil, nil, false, &sink, nil)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(sink.Bytes(), []byte("9007199254740993")) {
		t.Fatal(sink.String())
	}
}

func TestEncodedRemoteDoesNotInheritAnotherRepositoryScope(t *testing.T) {
	root := testRoot(t)
	path := filepath.Join(root, "session.jsonl")
	records := completed("test")
	records[0]["payload"] = Object{"id": "test", "git": Object{"repository_url": "https://github.com/example%2Fapp.git"}}
	writeRecords(t, path, records)
	_, reason, err := ScopeReason(path, Object{"repos": []any{Object{"id": "example/app", "information_scope": "private"}}})
	if err != nil {
		t.Fatal(err)
	}
	if reason == "" {
		t.Fatal("encoded URL inherited a different repository scope")
	}
}

func TestInvalidUTF8LinePreservesSurroundingVisibleItemsAndCompletedPartialSession(t *testing.T) {
	root := testRoot(t)
	path := filepath.Join(root, "session.jsonl")
	var source bytes.Buffer
	encoder := json.NewEncoder(&source)
	encoder.Encode(Object{"type": "session_meta", "payload": Object{"id": "test"}})
	encoder.Encode(Object{"type": "response_item", "payload": Object{"type": "message", "content": "Before invalid line"}})
	source.Write([]byte("{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"content\":\"\xff\"}}\n"))
	encoder.Encode(Object{"type": "response_item", "payload": Object{"type": "message", "content": "After invalid line"}})
	encoder.Encode(Object{"type": "event_msg", "payload": Object{"type": "task_complete"}})
	if err := os.WriteFile(path, source.Bytes(), 0600); err != nil {
		t.Fatal(err)
	}

	entry := entries(collectOK(t, options(root, path)))[0]

	if entry["status"] != "partial" || entry["visible_items"] != 2 {
		t.Fatal(entry)
	}
	failures := entry["errors"].([]Object)
	if len(failures) != 1 || failures[0]["line"] != 3 || failures[0]["error"] != "UnicodeDecodeError" {
		t.Fatal(failures)
	}
	lifecycle := entry["lifecycle"].([]Object)
	if len(lifecycle) != 2 || lifecycle[0]["line"] != 3 || lifecycle[0]["event"] != "unknown" || lifecycle[1]["event"] != "task_complete" {
		t.Fatal(lifecycle)
	}
	transcript, err := os.ReadFile(str(entry["transcript"]))
	if err != nil {
		t.Fatal(err)
	}
	decoder := json.NewDecoder(bytes.NewReader(transcript))
	for _, want := range []struct {
		line    int
		content string
	}{{2, "Before invalid line"}, {4, "After invalid line"}} {
		var item Object
		if err := decoder.Decode(&item); err != nil {
			t.Fatal(err)
		}
		if item["line"] != float64(want.line) || item["payload"].(Object)["content"] != want.content {
			t.Fatal(item)
		}
	}
	var extra Object
	if err := decoder.Decode(&extra); err != io.EOF {
		t.Fatal(err)
	}
	after, err := os.ReadFile(path)
	if err != nil || !bytes.Equal(after, source.Bytes()) {
		t.Fatal("source changed", err)
	}
}

func TestInvalidUTF8MetadataFailsScopeSelectionWithOriginalDecodeReason(t *testing.T) {
	root := testRoot(t)
	path := filepath.Join(root, "session.jsonl")
	source := []byte("{\"type\":\"session_meta\",\"payload\":{\"id\":\"\xff\",\"git\":{\"repository_url\":\"https://github.com/example/app.git\"}}}\n{unread body\n")
	if err := os.WriteFile(path, source, 0600); err != nil {
		t.Fatal(err)
	}
	o := options(root, path)
	o.Source = Object{"repos": []any{Object{"id": "example/app"}}}

	result := collectOK(t, o)

	entry := entries(result)[0]
	if counts(result)["failed"] != 1 || entry["reason"] != "UnicodeDecodeError" {
		t.Fatal(result)
	}
	if entry["transcript"] != nil {
		t.Fatal("invalid metadata exported a visible body")
	}
	paths, err := filepath.Glob(filepath.Join(o.Output, "session-*"))
	if err != nil || len(paths) != 0 {
		t.Fatal(paths, err)
	}
}
