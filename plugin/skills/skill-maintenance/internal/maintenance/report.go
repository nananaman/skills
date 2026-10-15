package maintenance

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
	_ "time/tzdata"
	"unicode"
	"unicode/utf8"

	"github.com/nananaman/skills/plugin/skills/skill-maintenance/assets"
)

var results = map[string]string{"passed": "成功", "failed": "失敗", "partial": "一部確認", "unverified": "未確認"}
var outcomes = map[string]string{"draft": "draft PR", "adopted": "採用済み", "proposed": "提案", "no_change": "変更なし", "failed": "失敗"}
var sessionStates = map[string]string{"read": "取得済み", "partial": "部分取得", "failed": "取得失敗", "uncollected": "未回収", "in_progress": "進行中", "held": "保留", "outside_period": "期間外", "excluded": "除外"}
var decisions = map[string]string{"adopted": "採用", "rejected": "見送り", "held": "保留", "no_change": "変更不要", "proposed": "提案"}

func objectFields(value any, required, optional []string) (Object, error) {
	object, ok := value.(map[string]any)
	if !ok {
		return nil, errors.New("report object has missing or unknown fields")
	}
	allowed := map[string]bool{}
	for _, key := range required {
		if _, ok := object[key]; !ok {
			return nil, errors.New("report object has missing or unknown fields")
		}
		allowed[key] = true
	}
	for _, key := range optional {
		allowed[key] = true
	}
	for key := range object {
		if !allowed[key] {
			return nil, errors.New("report object has missing or unknown fields")
		}
	}
	return object, nil
}
func stringFields(object Object, keys []string) error {
	for _, key := range keys {
		if value, exists := object[key]; exists {
			if _, ok := value.(string); !ok {
				return errors.New("report text fields must be strings")
			}
		}
	}
	return nil
}
func number(value any) (float64, bool) {
	switch n := value.(type) {
	case float64:
		return n, true
	case int:
		return float64(n), true
	case json.Number:
		f, err := n.Float64()
		return f, err == nil
	default:
		return 0, false
	}
}
func seconds(value any) error {
	if value == nil {
		return nil
	}
	n, ok := number(value)
	if !ok || math.IsNaN(n) || math.IsInf(n, 0) || n < 0 {
		return errors.New("seconds must be null or a finite nonnegative number")
	}
	return nil
}
func validateURL(value string) error {
	bad := func() error {
		return errors.New("pr_url must be an absolute HTTP(S) URL without credentials, query, fragment, or unsafe characters")
	}
	for _, character := range value {
		if unicode.IsSpace(character) || character < 32 || character == 127 || strings.ContainsRune("\\<>\"", character) {
			return bad()
		}
	}
	parsed, err := url.Parse(value)
	if err != nil || parsed.User != nil || parsed.Hostname() == "" || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.RawQuery != "" || parsed.Fragment != "" {
		return bad()
	}
	if port := parsed.Port(); port != "" {
		n, err := strconv.Atoi(port)
		if err != nil || n < 0 || n > 65535 {
			return bad()
		}
	}
	return nil
}
func list(report Object, key string) []any { value, _ := report[key].([]any); return value }
func valueOr(object Object, key, fallback string) string {
	if value, ok := object[key].(string); ok {
		return value
	}
	return fallback
}
func truthOr(object Object, key, fallback string) string {
	if value := str(object[key]); value != "" {
		return value
	}
	return fallback
}
func ValidateReport(report Object) error {
	if _, err := objectFields(report, []string{"version", "date", "timezone"}, []string{"summary", "period", "timing", "outcomes", "reflections", "checks", "remaining", "sessions"}); err != nil {
		return err
	}
	validVersion := false
	switch value := report["version"].(type) {
	case int:
		validVersion = value == 1
	case json.Number:
		validVersion = value.String() == "1"
	}
	if !validVersion {
		return errors.New("unsupported report version")
	}
	if err := stringFields(report, []string{"date", "timezone", "summary", "period"}); err != nil {
		return err
	}
	date, err := time.Parse("2006-01-02", str(report["date"]))
	if err != nil || date.Year() < 1 || date.Format("2006-01-02") != report["date"] {
		return errors.New("date must be YYYY-MM-DD")
	}
	zone := str(report["timezone"])
	if zone == "" || zone == "Local" {
		return errors.New("timezone must be an IANA timezone")
	}
	if _, err := time.LoadLocation(zone); err != nil {
		return errors.New("timezone must be an IANA timezone")
	}
	specs := []struct {
		name               string
		required, optional []string
		enums              map[string]map[string]string
	}{
		{"outcomes", []string{"title", "change", "status"}, []string{"pr_url"}, map[string]map[string]string{"status": outcomes}},
		{"reflections", []string{"title", "happened", "next", "result", "evidence"}, []string{"change", "decision", "overview"}, map[string]map[string]string{"result": results, "decision": decisions}},
		{"checks", []string{"title", "result", "detail"}, nil, map[string]map[string]string{"result": results}},
		{"remaining", []string{"title", "detail"}, nil, nil},
		{"sessions", []string{"title", "source", "evidence", "status", "detail"}, nil, map[string]map[string]string{"evidence": {"history": "", "self_report": ""}, "status": sessionStates}},
	}
	for _, spec := range specs {
		if value, exists := report[spec.name]; exists {
			if _, ok := value.([]any); !ok {
				return fmt.Errorf("%s must be a list", spec.name)
			}
		}
		for _, value := range list(report, spec.name) {
			item, err := objectFields(value, spec.required, spec.optional)
			if err != nil {
				return err
			}
			keys := append(append([]string{}, spec.required...), spec.optional...)
			for _, key := range keys {
				if key != "overview" {
					if err := stringFields(item, []string{key}); err != nil {
						return err
					}
				}
			}
			for key, values := range spec.enums {
				if value, exists := item[key]; exists {
					if _, ok := values[str(value)]; !ok {
						return fmt.Errorf("unknown %s.%s", spec.name, key)
					}
				}
			}
			if spec.name == "reflections" {
				if value, exists := item["overview"]; exists {
					overview, err := objectFields(value, []string{"title", "change", "evaluation", "reason"}, nil)
					if err != nil {
						return err
					}
					if err := stringFields(overview, []string{"title", "change", "evaluation", "reason"}); err != nil {
						return err
					}
				}
			}
			if spec.name == "outcomes" {
				if value, exists := item["pr_url"]; exists {
					if err := validateURL(str(value)); err != nil {
						return err
					}
				}
			}
		}
	}
	timing := Object{}
	if value, exists := report["timing"]; exists {
		var err error
		timing, err = objectFields(value, nil, []string{"start", "end", "wall_seconds", "scope", "stages"})
		if err != nil {
			return err
		}
	}
	if err := stringFields(timing, []string{"scope"}); err != nil {
		return err
	}
	if err := seconds(timing["wall_seconds"]); err != nil {
		return err
	}
	for _, key := range []string{"start", "end"} {
		if value := timing[key]; value != nil {
			if err := stringFields(timing, []string{key}); err != nil {
				return err
			}
			if _, err := instant(str(value)); err != nil {
				return err
			}
		}
	}
	if value, exists := timing["stages"]; exists {
		if _, ok := value.([]any); !ok {
			return errors.New("timing.stages must be a list")
		}
	}
	for _, value := range list(timing, "stages") {
		stage, err := objectFields(value, []string{"title", "seconds", "detail"}, nil)
		if err != nil {
			return err
		}
		if err := stringFields(stage, []string{"title", "detail"}); err != nil {
			return err
		}
		if err := seconds(stage["seconds"]); err != nil {
			return err
		}
	}
	return nil
}

var htmlEscape = strings.NewReplacer("&", "&amp;", "<", "&lt;", ">", "&gt;", "\"", "&quot;", "'", "&#x27;")

func text(value string) string { return htmlEscape.Replace(value) }

var markdownEscape = regexp.MustCompile("([\\\\`*_{}\\[\\]()#+.!|>\\-])")

func markdownText(value string) string {
	value = strings.NewReplacer("&", "&amp;", "<", "&lt;", ">", "&gt;").Replace(value)
	return markdownEscape.ReplaceAllString(value, `\$1`)
}
func table(headers []string, rows [][]string, cssClass string) string {
	var head, body strings.Builder
	for _, label := range headers {
		head.WriteString(`<th scope="col">` + text(label) + `</th>`)
	}
	for _, row := range rows {
		body.WriteString("<tr>")
		for _, cell := range row {
			body.WriteString("<td>" + cell + "</td>")
		}
		body.WriteString("</tr>")
	}
	return `<div class="table-scroll" tabindex="0" role="region" aria-label="` + text(headers[0]) + `の表"><table class="` + cssClass + `"><thead><tr>` + head.String() + `</tr></thead><tbody>` + body.String() + `</tbody></table></div>`
}
func section(identifier, title, content, empty string) string {
	if content == "" {
		content = "<p>" + text(empty) + "</p>"
	}
	return `<section aria-labelledby="` + identifier + `"><h2 id="` + identifier + `">` + text(title) + `</h2>` + content + `</section>`
}
func duration(value any) string {
	if value == nil {
		return "未計測"
	}
	n, _ := number(value)
	n = math.Floor(n)
	return fmt.Sprintf("%.0f分%.0f秒", math.Floor(n/60), math.Mod(n, 60))
}

type Rendered struct {
	HTML     string `json:"html"`
	Markdown string `json:"markdown"`
}

func RenderReport(report Object) (Rendered, error) {
	if err := ValidateReport(report); err != nil {
		return Rendered{}, err
	}
	date, zone := str(report["date"]), str(report["timezone"])
	summary, period := valueOr(report, "summary", "取得・振り返りの結果"), valueOr(report, "period", "記録なし")
	sections := []string{}
	md := []string{"# " + markdownText(date) + " スキル振り返り", "", "日付基準：" + markdownText(zone), "", "対象期間：" + markdownText(period), "", markdownText(summary), ""}
	outcomeRows := [][]string{}
	md = append(md, "## 今日の成果", "")
	adopted := 0
	for _, value := range list(report, "outcomes") {
		item := value.(Object)
		body := "<p>" + text(str(item["change"])) + "</p>"
		if str(item["pr_url"]) != "" {
			body += `<a class="pr-link" href="` + text(str(item["pr_url"])) + `" target="_blank" rel="noopener noreferrer">PRを開く ↗</a>`
		}
		outcomeRows = append(outcomeRows, []string{text(outcomes[str(item["status"])]), text(str(item["title"])), body})
		md = append(md, "### "+markdownText(str(item["title"])), "", "状態："+outcomes[str(item["status"])], "", markdownText(str(item["change"])), "")
		if str(item["pr_url"]) != "" {
			md = append(md, "[PRを開く](<"+str(item["pr_url"])+">)", "")
		}
		if item["status"] == "adopted" {
			adopted++
		}
	}
	content := ""
	if len(outcomeRows) > 0 {
		content = table([]string{"状態", "成果", "変更内容"}, outcomeRows, "")
	} else {
		md = append(md, "成果はありません。", "")
	}
	sections = append(sections, section("outcomes", "今日の成果", content, "成果はありません。"))
	reflectionRows, detailRows := [][]string{}, [][]string{}
	md = append(md, "## 採用と判断", "")
	for _, value := range list(report, "reflections") {
		item := value.(Object)
		result := str(item["result"])
		decision, exists := decisions[str(item["decision"])]
		if !exists {
			decision = "判断未記載"
		}
		overview, explicit := item["overview"].(Object)
		if !explicit {
			overview = Object{"title": item["title"], "change": truthOr(item, "change", "変更は未実施"), "evaluation": results[result] + "：" + str(item["evidence"]), "reason": item["next"]}
		}
		reflectionRows = append(reflectionRows, []string{text(decision), "<strong>" + text(str(overview["title"])) + "</strong><p>" + text(str(overview["change"])) + "</p>", "<p>" + text(str(overview["evaluation"])) + "</p><p>" + text(str(overview["reason"])) + "</p>"})
		md = append(md, "### "+markdownText(str(item["title"])), "", "判断："+decision, "")
		if explicit {
			for _, pair := range [][2]string{{"概要の案名", "title"}, {"変更の要点", "change"}, {"実評価", "evaluation"}, {"判断理由", "reason"}} {
				md = append(md, "**"+pair[0]+"**："+markdownText(str(overview[pair[1]])), "")
			}
		}
		for _, pair := range [][2]string{{"何が起きた", str(item["happened"])}, {"次にどうする", str(item["next"])}, {"変更・対応", truthOr(item, "change", "変更は未実施")}, {"検証", results[result]}, {"根拠", str(item["evidence"])}} {
			detailRows = append(detailRows, []string{text(str(item["title"])), text(pair[0]), text(pair[1])})
			md = append(md, "**"+pair[0]+"**："+markdownText(pair[1]), "")
		}
	}
	content = ""
	if len(reflectionRows) > 0 {
		content = table([]string{"判断", "案と変更内容", "実評価と判断理由"}, reflectionRows, "decisions") + `<details><summary>反省点と次の対応・根拠の全文</summary>` + table([]string{"案", "項目", "内容"}, detailRows, "") + `</details>`
	} else {
		md = append(md, "反省点はありません。未分析・取得失敗は検証結果と残件に記載します。", "")
	}
	sections = append(sections, section("reflections", "採用と判断", content, "反省点はありません。未分析・取得失敗は検証結果と残件を参照してください。"))
	md = append(md, "## 検証結果", "")
	checkRows := [][]string{}
	for _, value := range list(report, "checks") {
		item := value.(Object)
		checkRows = append(checkRows, []string{text(str(item["title"])), text(results[str(item["result"])]), text(str(item["detail"]))})
		md = append(md, "### "+markdownText(str(item["title"]))+" — "+results[str(item["result"])], "", markdownText(str(item["detail"])), "")
	}
	content = ""
	if len(checkRows) > 0 {
		content = table([]string{"確認", "状態", "内容"}, checkRows, "")
	} else {
		md = append(md, "検証結果はありません。", "")
	}
	sections = append(sections, section("checks", "検証結果", content, "検証結果はありません。"))
	md = append(md, "## 残件・判断待ち", "")
	remainingRows := [][]string{}
	for _, value := range list(report, "remaining") {
		item := value.(Object)
		remainingRows = append(remainingRows, []string{text(str(item["title"])), text(str(item["detail"]))})
		md = append(md, "### "+markdownText(str(item["title"])), "", markdownText(str(item["detail"])), "")
	}
	content = ""
	if len(remainingRows) > 0 {
		content = table([]string{"未了事項", "理由と次の対応"}, remainingRows, "")
	} else {
		md = append(md, "記録された残件はありません。", "")
	}
	sections = append(sections, section("remaining", "残件・判断待ち", content, "記録された残件はありません。"))
	md = append(md, "## 対象一覧", "")
	sessionRows := [][]string{}
	for _, value := range list(report, "sessions") {
		item := value.(Object)
		evidence := "自己申告"
		if item["evidence"] == "history" {
			evidence = "履歴の観測"
		}
		sessionRows = append(sessionRows, []string{text(str(item["title"])), text(str(item["source"]) + " · " + evidence + " · " + sessionStates[str(item["status"])]), text(str(item["detail"]))})
		md = append(md, "### "+markdownText(str(item["title"])), "", markdownText(str(item["source"]))+"・"+evidence+"・"+sessionStates[str(item["status"])], "", markdownText(str(item["detail"])), "")
	}
	content = ""
	if len(sessionRows) > 0 {
		content = `<details><summary>対象ごとの取得状態・結果・未確認事項</summary>` + table([]string{"対象", "入力元と取得状態", "確認した内容"}, sessionRows, "") + `</details>`
	} else {
		md = append(md, "記録された対象はありません。取得失敗とは区別してください。", "")
	}
	sections = append(sections, section("sessions", "対象一覧", content, "記録された対象はありません。取得失敗とは区別してください。"))
	timing, _ := report["timing"].(Object)
	wall := duration(timing["wall_seconds"])
	timePairs := [][2]string{{"開始", truthOr(timing, "start", "未計測")}, {"終了", truthOr(timing, "end", "未計測")}, {"全体wall time", wall}, {"計測範囲・再利用条件", truthOr(timing, "scope", "記録なし")}}
	timeRows := [][]string{}
	md = append(md, "## 時間", "")
	for _, pair := range timePairs {
		timeRows = append(timeRows, []string{text(pair[0]), text(pair[1])})
		md = append(md, "**"+pair[0]+"**："+markdownText(pair[1]), "")
	}
	content = table([]string{"計測項目", "内容"}, timeRows, "")
	stageRows := [][]string{}
	for _, value := range list(timing, "stages") {
		stage := value.(Object)
		elapsed := duration(stage["seconds"])
		stageRows = append(stageRows, []string{text(str(stage["title"])), elapsed, text(str(stage["detail"]))})
		md = append(md, "### "+markdownText(str(stage["title"]))+" — "+elapsed, "", markdownText(str(stage["detail"])), "")
	}
	if len(stageRows) > 0 {
		content += table([]string{"段階", "実測", "計測範囲"}, stageRows, "")
	}
	sections = append(sections, section("timing", "時間", content, "時間は未計測です。"))
	metrics := fmt.Sprintf("採用済み成果 %d件 · 実測 %s", adopted, wall)
	document := strings.NewReplacer("$date", text(date), "$timezone", text(zone), "$period", text(period), "$summary", text(summary), "$metrics", metrics, "$sections", strings.Join(sections, "")).Replace(assets.ReportTemplate)
	if len(document) > 256*1024 {
		return Rendered{}, errors.New("HTML exceeds the Page visualization limit of 256 KiB; preserve JSON and shorten the overview")
	}
	return Rendered{document, strings.Join(md, "\n")}, nil
}

// DecodeReport preserves number syntax so version 1.0 cannot silently become 1.
func DecodeReport(data []byte) (Object, error) {
	if !utf8.Valid(data) {
		return nil, errors.New("report JSON must be UTF-8")
	}
	var report Object
	decoder := json.NewDecoder(strings.NewReader(string(data)))
	decoder.UseNumber()
	if err := decoder.Decode(&report); err != nil {
		return nil, err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return nil, errors.New("report must contain one JSON object")
	}
	return report, nil
}
func RenderFile(input, repo, output string) (Object, error) {
	return renderFile(input, repo, output, createPrivate)
}
func renderFile(input, repo, output string, create func(string) (*os.File, error)) (Object, error) {
	source, err := os.ReadFile(input)
	if err != nil {
		return nil, err
	}
	report, err := DecodeReport(source)
	if err != nil {
		return nil, err
	}
	rendered, err := RenderReport(report)
	if err != nil {
		return nil, err
	}
	if err := PrivateDirectory(output, repo); err != nil {
		return nil, err
	}
	paths := Object{}
	for _, artifact := range []struct{ kind, name, body string }{{"html", "report.html", rendered.HTML}, {"markdown", "report.md", rendered.Markdown}} {
		path := filepath.Join(output, artifact.name)
		f, err := create(path)
		if err != nil {
			return nil, err
		}
		_, err = f.WriteString(artifact.body)
		closeErr := f.Close()
		if err != nil {
			return nil, err
		}
		if closeErr != nil {
			return nil, closeErr
		}
		paths[artifact.kind] = path
	}
	digest := sha256.Sum256(source)
	paths["json_sha256"] = hex.EncodeToString(digest[:])
	paths["html_bytes"] = len(rendered.HTML)
	return paths, nil
}
