---
name: review-diff-skill
description: skill 変更 diff を commit / push / APM pin / install 前に必ずレビューする。description、本文手順、safety、配布導線の regression を検出し、actionable finding が残る間は先へ進ませない。
---

skill の変更差分を、配布前 gate としてレビューする。
対象は diff であり、skill 全体の棚卸しは `review-skill` に委譲する。

## Contract

- skill に関する `git commit`、push、APM pin 更新、`apm install -g` の前に必ず実行する。
- actionable finding がある場合は修正し、再度 `review-diff-skill` を実行する。
- actionable finding が残っている状態で commit / push / pin / install へ進まない。
- ユーザーの明示依頼なしに commit / push / pin / install しない。
- `reviewing-skills` の共通 rubric を必ず適用する。

## Workflow

1. レビュー対象を決める。
   - dirty worktree があれば local diff を対象にする。
   - commit 済みなら commit diff、branch 作業なら branch diff を対象にする。
   - skill 以外の変更が混ざっていれば、skill 変更とそれ以外を分けて扱う。

2. diff を読む。
   - 変更された `SKILL.md`、`references/`、`GLOSSARY.md`、`README.md`、APM 設定を確認する。
   - description と本文手順の対応を確認する。
   - 追加・削除された手順が、agent の実行順と停止条件を変えていないか確認する。

3. `reviewing-skills` の Level 0: Static consistency を必ず実行する。
   - description / body consistency を確認する。
   - 変更された trigger branch が本文 workflow と対応しているか確認する。
   - scope gap があれば、commit / push / pin / install へ進まない。

4. 重要変更では `reviewing-skills` の Level 1: Scenario walkthrough を実行する。
   - 新規 skill、model-invoked skill の description 変更、高頻度利用 skill、過去に誤作動した skill、大幅変更では必須。
   - commit / push / APM pin 更新 / install 前の重要変更でも必須。
   - median scenario 1 件と edge scenario 1〜2 件で、変更後の workflow が期待通りたどれるか確認する。

5. さらに高リスクなら `reviewing-skills` の Level 2: Independent executor trial を実行する。
   - Level 1 で `[critical]` 相当の穴が見つかった場合。
   - レビュー対象 skill が agent の自律行動や Git / 配布操作を制御する場合。
   - author の読みだけでは挙動を判断しづらい場合。

6. diff 固有の regression を見る。
   - 変更前より trigger が広がりすぎていないか、狭まりすぎていないか。
   - 新しい手順が既存の停止条件を迂回していないか。
   - 削除された文が safety gate、user confirmation、failure handling を担っていなかったか。
   - README、APM 設定、skill 名、配置が本文と矛盾していないか。

7. 必要に応じて全体レビューへ escalate する。
   - 新規 skill。
   - model-invoked skill の description を変えた。
   - 高頻度利用 skill。
   - 過去に誤作動した skill。
   - skill の責務や workflow を大きく変えた。
   - 上記に当たる場合は `review-skill` を実行する。

8. finding を検証する。
   - reviewer の finding をそのまま採用しない。
   - 対象 diff と周辺本文を直接読み、根拠が確認できるものだけ accepted にする。
   - speculative risk、cosmetic nit、好み、過剰な rewrite は rejected にする。

9. closeout する。
   - accepted finding があれば修正し、再レビューする。
   - actionable finding がなければ、commit / push / pin / install の前提条件を満たしたと報告する。
   - ただし実際の commit / push / pin / install は、ユーザーが明示依頼した場合だけ行う。

## Output

finding の有無に関係なく、review loop に必要な metadata を必ず報告する。

```md
## Evaluation
- reviewing-skills Level: Level 0 / Level 1 / Level 2 のどこまで実行したか
- Escalated to review-skill: yes / no と理由
- Accepted findings: 件数と要約
- Rejected findings: 件数と理由
- Safety: commit / push / APM pin update / install は未実行

## Findings

### [severity] title
- Target: path:line
- Problem: agent がどう誤作動するか、または何が保守しづらくなるか
- Axis: description / predictability / hierarchy / completion / pruning / failure modes / safety
- Evidence: diff、既存 skill 本文、reviewing-skills rubric / scenario 結果からの根拠
- Suggested fix: 最小修正
- Judgment link: この修正が満たす requirements checklist / 判定文言

## Trace summary
- Weak phase: Understanding / Planning / Execution / Formatting / none
- Unclear points: 要約
- Discretionary fill-ins: 要約
- Retries: 回数と理由
```

finding がない場合は、`## Findings` に actionable finding がないことを明示する。
