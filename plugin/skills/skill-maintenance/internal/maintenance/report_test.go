package maintenance

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"math"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func baseReport() Object { return Object{"version": 1, "date": "2026-10-07", "timezone": "Asia/Tokyo"} }
func renderOK(t *testing.T, report Object) Rendered {
	t.Helper()
	result, err := RenderReport(report)
	if err != nil {
		t.Fatal(err)
	}
	return result
}
func both(t *testing.T, result Rendered, values ...string) {
	t.Helper()
	for _, document := range []string{result.HTML, result.Markdown} {
		for _, value := range values {
			if !strings.Contains(document, value) {
				t.Fatalf("missing %q", value)
			}
		}
	}
}
func TestDecisionTablePreservesExplicitJudgmentAndFullEvidence(t *testing.T) {
	reflection := Object{"title": "元の案", "happened": "長い経緯", "next": "追加の入力を用意する", "change": "実装候補", "result": "passed", "evidence": "限定した確認は成功", "decision": "held", "overview": Object{"title": "短い案名", "change": "変更の要点", "evaluation": "比較0実行", "reason": "因果関係は未確認"}}
	report := baseReport()
	report["reflections"] = []any{reflection}
	result := renderOK(t, report)
	both(t, result, "成果はありません", "保留", "短い案名", "変更の要点", "比較0実行", "因果関係は未確認", "長い経緯", "追加の入力を用意する", "実装候補", "限定した確認は成功")
	if !strings.Contains(result.HTML, "<table") || !strings.Contains(result.HTML, "<details") {
		t.Fatal("tables and full details missing")
	}
	delete(reflection, "decision")
	if !strings.Contains(renderOK(t, report).HTML, "判断未記載") {
		t.Fatal("missing unknown decision")
	}
	for _, invalid := range []Object{{"decision": "unknown"}, {"overview": Object{"title": "不足"}}, {"overview": Object{"title": "title", "change": "change", "evaluation": "evaluation", "reason": 1}}} {
		copy := Object{}
		for key, value := range reflection {
			copy[key] = value
		}
		for key, value := range invalid {
			copy[key] = value
		}
		report["reflections"] = []any{copy}
		if _, err := RenderReport(report); err == nil {
			t.Fatal(invalid)
		}
	}
}
func TestDurationsUseMinutesSecondsWithoutMutatingPreciseInput(t *testing.T) {
	report := baseReport()
	report["timing"] = Object{"wall_seconds": 1471.333666, "stages": []any{Object{"title": "秒未満", "seconds": 0.9, "detail": "端数は表示で切り捨て"}, Object{"title": "一分", "seconds": 60, "detail": "境界"}, Object{"title": "未計測", "seconds": nil, "detail": "未知"}}}
	before, _ := json.Marshal(report)
	result := renderOK(t, report)
	after, _ := json.Marshal(report)
	if !bytes.Equal(before, after) {
		t.Fatal("mutated report")
	}
	both(t, result, "24分31秒", "0分0秒", "1分0秒", "未計測")
	if strings.Contains(result.HTML, "1471.333666秒") {
		t.Fatal("display used raw seconds")
	}
}
func TestPeriodCountsAndReaderHoldReasonsArePreserved(t *testing.T) {
	report := baseReport()
	period := "2026-10-05 03:51:53 JST以上、2026-10-07 17:40 JST未満"
	count := "発見3・対象2・取得1・振り返り1・保留1・期間外1"
	report["period"] = period
	report["checks"] = []any{Object{"title": "取得範囲", "result": "partial", "detail": count}}
	report["sessions"] = []any{Object{"title": "終了不明", "source": "Mac", "evidence": "history", "status": "held", "detail": "終了を確認できず本文を保留"}, Object{"title": "期間外", "source": "Mac", "evidence": "history", "status": "outside_period", "detail": "指定期間に活動なし"}}
	result := renderOK(t, report)
	both(t, result, count, "終了を確認できず本文を保留", "指定期間に活動なし")
	if !strings.Contains(result.HTML, period) || !strings.Contains(result.Markdown, strings.ReplaceAll(period, "-", `\-`)) {
		t.Fatal("period changed")
	}
}
func TestIOFailurePreservesInputAndPartialEvidence(t *testing.T) {
	root := testRoot(t)
	input := filepath.Join(root, "input.json")
	source, _ := json.Marshal(baseReport())
	os.WriteFile(input, source, 0600)
	output := filepath.Join(root, "output")
	create := func(path string) (*os.File, error) {
		if filepath.Base(path) == "report.md" {
			return nil, errors.New("synthetic write failure")
		}
		return createPrivate(path)
	}
	if _, err := renderFile(input, filepath.Join(root, "repo"), output, create); err == nil {
		t.Fatal("write failure returned success")
	}
	after, _ := os.ReadFile(input)
	if !bytes.Equal(source, after) {
		t.Fatal("changed source")
	}
	if _, err := os.Stat(filepath.Join(output, "report.html")); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(output, "report.md")); !os.IsNotExist(err) {
		t.Fatal("markdown unexpectedly exists")
	}
}
func TestHTMLAndMarkdownEscapeUntrustedTextWithoutExecutableJSON(t *testing.T) {
	attack := "</script><img src=\"https://example.com/tracker\" onerror=\"alert(1)\">\n[click](javascript:alert(1)) $sections & '\""
	report := baseReport()
	report["summary"] = attack
	report["reflections"] = []any{Object{"title": attack, "happened": attack, "next": attack, "result": "unverified", "evidence": attack, "decision": "held", "overview": Object{"title": attack, "change": attack, "evaluation": attack, "reason": attack}}}
	result := renderOK(t, report)
	for _, document := range []string{result.HTML, result.Markdown} {
		if strings.Contains(document, "<img") || strings.Contains(document, "<script>") {
			t.Fatal("executable HTML included")
		}
	}
	if !strings.Contains(result.HTML, "&lt;/script&gt;") || !strings.Contains(result.HTML, "$sections") || strings.Contains(result.Markdown, "[click](javascript:") {
		t.Fatal("escaping or nonrecursive substitution failed")
	}
	if !strings.Contains(result.HTML, "&#x27;&quot;") {
		t.Fatal("quote escaping changed")
	}
}
func TestEmptyFailedAndUnverifiedReportsKeepUnknownResultsExplicit(t *testing.T) {
	both(t, renderOK(t, baseReport()), "成果はありません", "未計測")
	report := baseReport()
	report["checks"] = []any{Object{"title": "取得", "result": "failed", "detail": "合成の取得失敗"}}
	report["remaining"] = []any{Object{"title": "再取得", "detail": "未分析"}}
	both(t, renderOK(t, report), "合成の取得失敗", "未分析")
}
func TestLongUnicodeIsPreservedAndEmbeddingLimitRefusesOversizedHTML(t *testing.T) {
	report := baseReport()
	long := strings.Repeat("長い合成結果\n", 1500)
	report["summary"] = long
	both(t, renderOK(t, report), long)
	report["summary"] = strings.Repeat("長", 100000)
	if _, err := RenderReport(report); err == nil || !strings.Contains(err.Error(), "256 KiB") {
		t.Fatal(err)
	}
}
func TestFileOutputsArePrivatePreserveJSONAndRefuseExistingOrGitOutput(t *testing.T) {
	root := testRoot(t)
	repo := filepath.Join(root, "repo")
	os.MkdirAll(filepath.Join(repo, ".git"), 0700)
	input := filepath.Join(root, "report.json")
	source, _ := json.Marshal(baseReport())
	os.WriteFile(input, source, 0600)
	output := filepath.Join(root, "rendered")
	result, err := RenderFile(input, repo, output)
	if err != nil {
		t.Fatal(err)
	}
	after, _ := os.ReadFile(input)
	if !bytes.Equal(after, source) {
		t.Fatal("input changed")
	}
	digest := sha256.Sum256(source)
	if result["json_sha256"] != hex.EncodeToString(digest[:]) {
		t.Fatal(result)
	}
	info, _ := os.Stat(output)
	if info.Mode().Perm() != 0700 {
		t.Fatal(info.Mode())
	}
	paths, err := os.ReadDir(output)
	if err != nil || len(paths) != 2 {
		t.Fatal(paths, err)
	}
	for _, path := range paths {
		info, _ := path.Info()
		if info.Mode().Perm() != 0600 {
			t.Fatal(info.Mode())
		}
	}
	preserved, _ := os.ReadFile(filepath.Join(output, "report.html"))
	if result["html_bytes"] != len(preserved) {
		t.Fatal(result)
	}
	if _, err := RenderFile(input, repo, output); err == nil {
		t.Fatal("accepted existing output")
	}
	repeated, _ := os.ReadFile(filepath.Join(output, "report.html"))
	if !bytes.Equal(preserved, repeated) {
		t.Fatal("existing output changed")
	}
	if _, err := RenderFile(input, repo, filepath.Join(repo, "rendered")); err == nil {
		t.Fatal("accepted Git output")
	}
}
func TestThinDataContractRejectsUnknownFieldsBadTypesStatesAndTime(t *testing.T) {
	cases := []Object{{"raw_log": "synthetic private source"}, {"version": true}, {"version": 2}, {"version": json.Number("1.0")}, {"date": "not-a-date"}, {"timezone": "Unknown/Zone"}, {"timezone": "Local"}, {"timezone": ""}, {"summary": Object{"nested": "not text"}}, {"checks": "not a list"}, {"checks": []any{Object{"title": "確認", "result": "clean", "detail": "未確認"}}}, {"remaining": []any{Object{"title": "確認", "detail": "保留", "private_path": "/synthetic"}}}, {"sessions": []any{Object{"title": "確認", "source": "Mac", "evidence": "verified", "status": "read", "detail": ""}}}, {"timing": Object{"wall_seconds": true}}, {"timing": Object{"wall_seconds": -1}}, {"timing": Object{"wall_seconds": math.NaN()}}, {"timing": Object{"start": "2026-10-07T09:00:00"}}, {"timing": nil}, {"timing": Object{"stages": nil}}, {"checks": nil}, {"timing": Object{"stages": []any{Object{"title": "x", "detail": "x", "seconds": "3"}}}}}
	for _, change := range cases {
		report := baseReport()
		for key, value := range change {
			report[key] = value
		}
		if _, err := RenderReport(report); err == nil {
			t.Fatalf("accepted: %v", change)
		}
	}
}
func TestLinksRejectExecutableLocalCredentialedAndAmbiguousURLs(t *testing.T) {
	credentialedURL := &url.URL{Scheme: "https", Host: "example.com", User: url.UserPassword("synthetic-user", "synthetic-password"), Path: "/pr"}
	for _, link := range []string{"javascript:alert(1)", "data:text/html,test", "file:///private/example", "//example.com/pr", credentialedURL.String(), "https://example.com/\npr", "https://example.com/\" onclick=\"alert(1)", "https://example.com\\@other.example/pr", "https://example.com/pull/1?access_token=synthetic", "https://example.com/pull/1#token=synthetic", "https://example.com:65536/pr", "https://example.com:abc/pr"} {
		report := baseReport()
		report["outcomes"] = []any{Object{"title": "合成PR", "change": "合成変更", "status": "draft", "pr_url": link}}
		if _, err := RenderReport(report); err == nil {
			t.Fatalf("accepted: %s", link)
		}
	}
}
func TestOutputOrderingAndDeterministicRenderingPreserveConnectedReflection(t *testing.T) {
	report := baseReport()
	report["outcomes"] = []any{Object{"title": "合成の改善", "change": "読みやすい出力へ変更", "status": "draft", "pr_url": "https://example.com/pull/1"}}
	report["reflections"] = []any{Object{"title": "合成の反省", "happened": "最後の確認が漏れた", "next": "最終編集後に確認する", "change": "確認手順を更新", "result": "passed", "evidence": "合成の確認が成功"}}
	report["checks"] = []any{Object{"title": "合成検証", "result": "passed", "detail": "1件成功"}}
	report["remaining"] = []any{Object{"title": "採用判断", "detail": "draftの内容を確認"}}
	report["sessions"] = []any{Object{"title": "合成実務", "source": "Mac", "evidence": "history", "status": "read", "detail": "観測した範囲を整理"}}
	report["timing"] = Object{"start": nil, "end": nil, "wall_seconds": nil, "scope": "全体は未計測", "stages": []any{}}
	result := renderOK(t, report)
	if result != renderOK(t, report) {
		t.Fatal("nondeterministic output")
	}
	both(t, result, "最後の確認が漏れた", "最終編集後に確認する", "確認手順を更新", "合成の確認が成功", "https://example.com/pull/1")
	for _, document := range []string{result.HTML, result.Markdown} {
		last := -1
		for _, title := range []string{"今日の成果", "採用と判断", "検証結果", "残件・判断待ち", "対象一覧", "時間"} {
			position := strings.Index(document, title)
			if position <= last {
				t.Fatal("section order changed")
			}
			last = position
		}
	}
}
func TestDecodeReportRejectsTrailingJSONAndPreservesVersionNumberSyntax(t *testing.T) {
	for _, source := range []string{`{"version":1,"date":"2026-10-07","timezone":"Asia/Tokyo"} {}`, `{"version":1.0,"date":"2026-10-07","timezone":"Asia/Tokyo"}`, `null`, `[]`} {
		report, err := DecodeReport([]byte(source))
		if err == nil {
			_, err = RenderReport(report)
		}
		if err == nil {
			t.Fatal(source)
		}
	}
}
