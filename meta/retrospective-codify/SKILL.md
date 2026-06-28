---
name: retrospective-codify
description: 明示依頼されたときだけ、試行錯誤で得た再利用可能な知見を ast-grep rule draft、既存 / 新規 skill、または AGENTS.md 系 source-of-truth へ固定する。失敗した初手、効いた解、次回の初動ルールを確認し、dedup check と承認を経て編集する。毎タスク終了時の自動起動、作業ログ保存、commit / push / APM pin / install には使わない。
disable-model-invocation: true
---

試行錯誤で得た「最初に知っていれば遠回りしなかった」知見を、次回の初動を変える形で固定する。
この skill は分類、重複確認、提案、承認後の編集までを担当する。
commit / push / APM pin 更新 / install は担当しない。

## 起動条件

明示依頼されたときだけ使う。

- 「今日の知見を固定して」
- 「codify して」
- 「retrospective しよう」
- 「これを skill / AGENTS.md / ast-grep rule に残したい」

次の場合は使わない。

- 単なる作業完了報告。
- 今回だけの作業ログやメモを残したいだけ。
- 再利用可能な初動ルールがない。
- commit / push / APM pin 更新 / install だけが目的。

## Workflow

1. 入力 3 点を固定する。
   - 失敗した初手: 最初に何をして、どう遠回りしたか。
   - 効いた解: 最終的に何が効いたか。
   - 次回の初動ルール: 次に似た状況で最初に何をするべきか。
   - 3 点が明示されていない場合は、会話履歴から仮説を作り、ユーザーに確認してから先へ進む。
   - 3 点を確認できない場合は codify しない。

2. 採用対象か判定する。
   - 「再利用可能で、次回の初動を変える知見」だけを採用候補にする。
   - project-specific かつ one-off な事情、単なる作業ログ、小さすぎる注意は採用せず session note に留める。
   - セキュリティ上公開できない内容は public skill repository へ置かない。

3. 出力先を分類する。
   - 機械的に検出できる code / config pattern なら、既存 linter または ast-grep rule draft を第一候補にする。
   - 短く、常時適用すべきで、判断を含まない指示なら AGENTS.md 系 source-of-truth の rule を候補にする。
   - 手順、文脈判断、テンプレート、複数 step を含むなら skill を候補にする。
   - どれにも当てはまらない場合は採用しない。

4. source-of-truth を探索する。
   - global の AGENTS.md rule は、dotfiles の `agents/AGENTS.md` を default source-of-truth とする。
   - project-local の常時 rule は、対象 repo の `AGENTS.md` を優先する。
   - `AGENTS.md` がなく、`CLAUDE.md`、Codex instructions、その他 agent instructions が source-of-truth らしい場合は、その実態を確認して候補にする。
   - `~/.claude/CLAUDE.md`、`~/.pi/agent/AGENTS.md`、`~/.config/codex/instructions.md` などのリンク先・展開先は直接編集しない。
   - 判断不能ならユーザーに質問する。

5. dedup check を必ず実行する。
   - 知見から検索キーを 2〜3 個作る。
   - 次を検索する。
     - 対象 repo の `AGENTS.md`、`CLAUDE.md`、Codex instructions などの agent instruction。
     - 対象 repo の project-local skills。
     - dotfiles の `agents/AGENTS.md`。
     - `nananaman/skills` の source-of-truth。
     - `~/.agents/skills` / `~/.claude/skills` の installed skill index。
     - 対象 repo の `sgconfig.yml`、`rules/`、`rule-tests/`、既存 linter 設定。
   - 結果を次のいずれかに分類する。
     - New: 近い既存知識がない。
     - Append to existing: 関連する rule / skill があり、追記・改善で足りる。
     - Duplicate: 既存知識で十分に covered。新規追加しない。
     - Undecidable: 重複か判断不能。ユーザーに確認する。

6. ast-grep rule 候補を作る場合は project-local 原則で扱う。
   - 対象 repo の `sgconfig.yml`、`rules/`、`rule-tests/` を第一候補にする。
   - global ast-grep rule は、基盤導入済みで source-of-truth が確認できる場合だけ候補にする。未導入なら future 候補として明示する。
   - `rules/*.yml` と `rule-tests/*-test.yml` の draft 案を出す。
   - ast-grep 基盤の導入、rule 実装、検証、CI 設定は専用 skill / 別作業に委譲する。

7. skill 候補を作る場合は既存改善を優先する。
   - 既存 skill に追記・修正できるなら、新規 skill を作らない。
   - 汎用 skill の source-of-truth は `nananaman/skills` とする。
   - project 固有 skill は対象 repo の project-local skills を候補にする。
   - `~/.agents/skills` / `~/.claude/skills` の展開物は直接編集しない。
   - skill を編集した場合は、編集後に `review-diff-skill` を実行する。

8. 提案を出して承認を待つ。
   - 承認前に AGENTS.md、skill、rule file を編集しない。
   - 提案には、分類理由、dedup 結果、対象 path、追加 / 変更案、次の action を含める。
   - Duplicate の場合は、どの既存記述で covered されたかを示して終了する。

9. 承認後に編集する。
   - 承認された対象だけを編集する。
   - skill を編集した場合は `review-diff-skill` を実行し、actionable finding があれば修正して再レビューする。
   - commit / push / APM pin 更新 / install は実行しない。必要なら次の導線として案内する。

## 出力形式

```md
## 判定
- 採用可否: 採用 / 不採用 / 要確認
- 出力先: ast-grep rule draft / 既存 skill 改善 / 新規 skill / AGENTS.md rule / session note
- 理由: <分類理由>

## 入力 3 点
- 失敗した初手: <内容>
- 効いた解: <内容>
- 次回の初動ルール: <内容>

## 重複確認
- 検索キー: `<key1>`, `<key2>`, `<key3>`
- 検索対象: <見た場所>
- 結果分類: New / Append to existing / Duplicate / Undecidable
- 根拠: <既存記述や不足分>

## 提案
- 対象: <path or future候補>
- 変更案: <追加・修正内容、または ast-grep rule draft の要約>

## 次のアクション
- <承認待ち / 編集後 review-diff-skill / 別 skill へ委譲 など>
```

## Done Criteria

- 入力 3 点が確認済みである。
- 再利用可能で次回の初動を変える知見か判定済みである。
- dedup check を実行し、New / Append / Duplicate / Undecidable の分類を報告している。
- 出力先と source-of-truth が明確である。
- 承認前に永続ファイルを編集していない。
- 編集した場合、対象と理由を報告している。
- skill 変更を行った場合、`review-diff-skill` を実行済みである。
- commit / push / APM pin 更新 / install を実行していない。
