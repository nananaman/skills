---
name: review-diff-skill
description: skill 変更 diff をレビューする。対象 diff が skill の routing、判断、手順、停止条件、出力形式に影響するかを冒頭で判定し、影響する場合は reviewing-skills の static contract check と smoke check で regression を検出する。単なる文書整理や実行契約に影響しない変更は skip decision で止める。
---

skill の変更差分をレビューする。
対象は diff であり、skill 全体の棚卸しは `review-skill` に委譲する。
共通の品質観点と smoke check protocol は `reviewing-skills` を必ず適用する。

## Contract

- この skill は、対象 skill の diff が agent の挙動をどう変えるかだけをレビューする。
- 対象 skill ディレクトリ外の配布・永続化操作は、この skill の責務外として扱う。
- この skill の実行中は、レビューに必要な読み取りと一時的な検証を超える永続化操作を実行しない。
- `SKILL.md` に触れている diff では呼び出してよい。ただし、冒頭の applicability check で実行契約に影響しないと判断したら skip する。
- actionable finding がある場合は、対象 diff と根拠を示し、最小修正を提案する。
- reviewer / subagent の finding はそのまま採用しない。対象 diff と周辺本文で根拠が確認できるものだけ accepted にする。

## Workflow

1. レビュー対象 diff を決める。
   - dirty worktree があれば local diff を対象にする。
   - commit 済みなら commit diff、branch 作業なら branch diff を対象にする。
   - skill 以外の変更が混ざっていれば、skill 変更とそれ以外を分けて扱う。

2. Applicability check を行う。
   - 変更された `SKILL.md`、`references/`、`GLOSSARY.md`、`assets/`、`scripts/`、関連 README を確認する。
   - diff が次のいずれかを変えるか判定する。
     - routing / discoverability。
     - agent の判断条件。
     - workflow の手順や順序。
     - 停止条件や escalation 条件。
     - 出力形式。
     - references / assets / scripts の使われ方。
     - safety / failure handling。
   - どれにも影響しない typo、formatting、リンク整理、一覧更新、説明の非実行的な整理だけなら skip decision を出して止める。
   - 迷う場合は対象として扱い、次へ進む。

3. Static contract check を実行する。
   - `reviewing-skills` の Static contract check を対象 diff に適用する。
   - `name:` と配置ディレクトリ、description の routing 条件、本文手順の対応を確認する。
   - 変更された trigger branch、workflow、停止条件、出力形式が本文内で一貫しているか確認する。
   - references / assets / scripts の追加・変更が progressive disclosure を守っているか確認する。

4. Smoke check を設計して実行する。
   - `reviewing-skills` の Smoke check protocol に従う。
   - 対象変更が実行契約に影響する場合、fresh agent / subagent による Execution smoke を省略しない。
   - subagent を使う場合は、harness が対応していれば background 実行し、verbose log の messages / tool calls / read files / commands / generated diff を evidence として確認する。
   - model-invoked skill の description / trigger 変更では、Discovery smoke も試みる。
   - Discovery smoke の harness-real な環境を用意できない場合は、未検証の残リスクとして報告し、Execution smoke で代替したと言わない。
   - checklist は skill 名や内部手順名ではなく、外部観測可能な期待結果で書く。
   - fresh agent / subagent を使えない場合は、実行不能理由と残リスクを報告し、smoke check 実行済みとは言わない。

5. Runtime smoke check が必要か判定する。
   - skill の期待動作が外部 CLI、ファイル生成、Git 操作、sandbox / temp repo、install、build、test、lint、API call などに依存する場合は、`reviewing-skills` の Runtime smoke check を実行する。
   - 実行できない場合は、理由と残リスクを報告する。

6. diff 固有の regression を見る。
   - 変更前より trigger が広がりすぎていないか、狭まりすぎていないか。
   - negative trigger の削除や曖昧化で近接領域に過発火しないか。
   - 新しい手順が既存の停止条件を迂回していないか。
   - 削除された文が safety gate、user confirmation、failure handling を担っていなかったか。
   - `SKILL.md` が肥大化し、通常 path に不要な context を積んでいないか。
   - 新しい `scripts/` が tiny CLI ではなく library code を抱えていないか、stdout / stderr で自己修正可能な結果を返すか。
   - README、skill 名、配置が本文と矛盾していないか。

7. 必要に応じて全体レビューへ escalate する。
   - 新規 skill。
   - model-invoked skill の description を変えた。
   - 高頻度利用 skill。
   - 過去に誤作動した skill。
   - skill の責務や workflow を大きく変えた。
   - 上記に当たる場合は `review-skill` を提案または実行する。

8. finding を検証する。
   - smoke check の failure と対象 diff を対応づける。
   - 対象 diff と周辺本文を直接読み、根拠が確認できるものだけ accepted にする。
   - speculative risk、cosmetic nit、好み、過剰な rewrite は rejected にする。

9. closeout する。
   - skip した場合は Skip decision だけを返す。
   - actionable finding があれば、対象 diff に紐づけて報告する。
   - actionable finding がなければ、Static contract check と smoke check を実施したうえで regression がないことを報告する。

## Output

### Skip decision

Applicability check で実行契約に影響しないと判断した場合は、通常の Findings 形式へ進まず、次だけを報告する。

```md
## Skip decision
- Reason: skill の routing / 判断 / 手順 / 停止条件 / 出力形式 / safety に影響しないため
- Checked diff: <対象ファイルと変更要約>
- Residual risk: <あれば短く。なければ none>
```

### Review result

finding の有無に関係なく、review loop に必要な metadata を必ず報告する。

```md
## Evaluation
- Applicability: 対象にした理由
- Static contract check: 実施結果の要約
- Smoke check: 実施 case、pass/fail、fresh agent / subagent を使ったか
- Runtime smoke check: 実施した / 不要 / 実施不能と理由
- Escalated to review-skill: yes / no と理由
- Accepted findings: 件数と要約
- Rejected findings: 件数と理由

## Smoke check

| Case | Input | Expected | Actual | Result | Evidence | Finding link |
| --- | --- | --- | --- | --- | --- | --- |
| <case> | <input> | <expected> | <actual> | pass/fail | <evidence> | <finding or —> |

## Findings

### [severity] title
- Target: path:line
- Problem: agent がどう誤作動するか、または何が保守しづらくなるか
- Axis: metadata / description / predictability / hierarchy / deterministic resources / completion / pruning / failure modes / safety
- Evidence: diff、既存 skill 本文、reviewing-skills rubric / smoke 結果からの根拠
- Suggested fix: 最小修正
- Judgment link: この修正が満たす smoke case の Expected / Result

## Trace summary
- Weak phase: Understanding / Planning / Execution / Formatting / none
- Unclear points: 要約
- Discretionary fill-ins: 要約
- Retries: 回数と理由
```

finding がない場合は、`## Findings` に actionable finding がないことを明示する。
