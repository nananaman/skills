---
name: review-skill
description: skill 全体を棚卸しして、責務過多、description / 本文不一致、手順抜け、参照肥大、誤発火・不発火、safety gap を洗い出す。skill の大幅変更、新規 skill、または「この skill が悪そう」という調査で使う。
---

agent skill 全体を、予測可能に動く小さな部品としてレビューする。
対象は diff ではなく skill 全体である。配布前の差分 gate は `review-diff-skill` を使う。
共通の品質観点は `reviewing-skills` を必ず適用する。

## Review Principles

- skill の目的は、確率的に振る舞う agent から予測可能なプロセスを引き出すこと。
- 予測可能性とは、毎回同じ出力を出すことではなく、毎回同じ種類の手順・判断・探索を行うことを指す。
- finding は high-confidence かつ action 可能なものだけに絞る。

## Workflow

1. 対象 skill と目的を確認する。
   - 対象の `SKILL.md`、`references/`、`GLOSSARY.md`、`NOTICE.md`、README 記載を読む。
   - その skill が解くべき作業、起動すべき場面、起動すべきでない場面を列挙する。

2. `reviewing-skills` の Level 0: Static consistency を必ず実行する。
   - description / body consistency を確認する。
   - scope gap があれば、scenario より先に description か本文の修正を提案する。

3. `reviewing-skills` の Level 1: Scenario walkthrough を必ず実行する。
   - median scenario 1 件と edge scenario 1〜2 件を作る。
   - requirements checklist を scenario ごとに 3〜7 個置き、少なくとも 1 つを `[critical]` にする。
   - 迷う分岐、本文にない discretionary fill-in、早すぎる完了、勝手な commit / push / pin / install へ進む導線を探す。

4. 必要なら `reviewing-skills` の Level 2: Independent executor trial を実行する。
   - 新規 skill、model-invoked skill、高頻度利用 skill、過去に誤作動した skill、大幅変更では Level 2 を使う。
   - executor の unclear points、discretionary fill-ins、retries を記録する。
   - executor の finding は本文で根拠を確認できるものだけ accepted にする。

5. 全体構造を評価する。
   - 1 skill に複数の責務が詰め込まれていないか。
   - model-invoked にすべき共通概念と user-invoked wrapper が混ざっていないか。
   - diff review、全体 review、作成 workflow、配布 workflow が混ざっていないか。
   - references がないと通常 path を実行できない構造になっていないか。

6. findings を整理する。
   - 対象本文と根拠が確認できるものだけ accepted にする。
   - speculative risk、cosmetic nit、好み、過剰な rewrite は rejected にする。
   - accepted finding は、どの品質軸を壊しているか明示する。

7. closeout する。
   - 課題一覧、優先度、推奨修正順を示す。
   - 修正を行った場合は `review-diff-skill` で差分レビューする。
   - `git commit`、push、APM pin 更新、`apm install -g` は、ユーザーが明示依頼した場合だけ実行する。

## Output

```md
## Findings

### [severity] title
- Target: path:line
- Axis: description / predictability / hierarchy / completion / pruning / failure modes / safety
- Problem: agent がどう誤作動するか、または何が保守しづらくなるか
- Evidence: skill 本文、description、scenario walkthrough からの根拠
- Suggested fix: 最小修正

## Evaluation
- Rubric: `reviewing-skills` を適用したこと
- Level 0: description / body consistency の結果
- Level 1: 実施した scenario と結果
- Level 2: 実施した / 省略した理由
- Accepted findings: 件数と要約
- Rejected findings: 件数と理由
```

finding がない場合は、`reviewing-skills` rubric と scenario walkthrough を実施したうえで actionable finding がないことを明示する。
