---
name: review-skill
description: skill 全体を棚卸しして、責務過多、metadata discoverability、positive / negative trigger、description / 本文不一致、progressive disclosure、deterministic resources、誤発火・不発火、safety gap を洗い出す。skill の大幅変更、新規 skill、または「この skill が悪そう」という調査で使う。
---

agent skill 全体を、予測可能に動く小さな部品としてレビューする。
対象は diff ではなく skill 全体である。差分に限定した review は `review-diff-skill` を使う。
共通の品質観点と smoke check protocol は `reviewing-skills` を必ず適用する。

## Review Principles

- skill の目的は、確率的に振る舞う agent から予測可能なプロセスを引き出すこと。
- 予測可能性とは、毎回同じ出力を出すことではなく、毎回同じ種類の手順・判断・探索を行うことを指す。
- finding は high-confidence かつ action 可能なものだけに絞る。
- 作者の静的読解だけで終えず、fresh agent / subagent による smoke check で、どの `SKILL.md` を読んでどう実行したかを確認する。
- この skill の実行中は、レビューに必要な読み取りと一時的な検証を超える永続化操作を実行しない。

## Workflow

1. 対象 skill と目的を確認する。
   - 対象の `SKILL.md`、`references/`、`GLOSSARY.md`、`assets/`、`scripts/`、`NOTICE.md`、README 記載を読む。
   - その skill が解くべき作業、起動すべき場面、起動すべきでない場面を列挙する。
   - `name:` と配置ディレクトリ、description の positive / negative trigger を確認する。

2. Static contract check を実行する。
   - `reviewing-skills` の Static contract check を対象 skill 全体に適用する。
   - metadata / discoverability と description / body consistency を確認する。
   - description が skill 読み込み前の routing 情報として十分か確認する。
   - workflow、分岐条件、停止条件、出力形式が agent に判定可能か確認する。
   - scope gap があれば、smoke check より先に description か本文の修正を提案する。

3. Smoke check を設計して実行する。
   - `reviewing-skills` の Smoke check protocol に従う。
   - fresh agent / subagent による Execution smoke を省略しない。
   - model-invoked skill では、Discovery smoke も試みる。
   - Discovery smoke の harness-real な環境を用意できない場合は、未検証の残リスクとして報告し、Execution smoke で代替したと言わない。
   - 新規 skill、高頻度利用 skill、過去に誤作動した skill、大幅変更では、境界条件や過去の failure pattern を含む追加 case を設計する。
   - checklist は skill 名や内部手順名ではなく、外部観測可能な期待結果で書く。
   - subagent を使う場合は、harness が対応していれば background 実行し、verbose log の messages / tool calls / read files / commands / generated diff を evidence として確認する。
   - fresh agent / subagent を使えない場合は、実行不能理由と残リスクを報告し、smoke check 実行済みとは言わない。

4. Runtime smoke check が必要か判定する。
   - skill の期待動作が外部 CLI、ファイル生成、Git 操作、sandbox / temp repo、install、build、test、lint、API call などに依存する場合は、`reviewing-skills` の Runtime smoke check を実行する。
   - 実行できない場合は、理由と残リスクを報告する。

5. 全体構造を評価する。
   - 1 skill に複数の責務が詰め込まれていないか。
   - model-invoked にすべき共通概念と user-invoked wrapper が混ざっていないか。
   - diff review、全体 review、作成 workflow、配布 workflow が混ざっていないか。
   - `SKILL.md` が通常 500 行未満で、agent の初期 context に置くべき手順へ絞られているか。
   - references がないと通常 path を実行できない構造になっていないか。
   - references / assets / scripts が原則 1 階層で、本文から必要時にだけ読まれる構造か。
   - README、CHANGELOG、INSTALLATION guide などの人間向け文書が、agent 向け実行契約と二重管理になっていないか。
   - scripts がある場合、tiny CLI として壊れやすい処理を固定し、stdout / stderr / exit status で agent に自己修正情報を返すか。

6. findings を整理する。
   - smoke check の failure と対象本文を対応づける。
   - 対象本文と根拠が確認できるものだけ accepted にする。
   - speculative risk、cosmetic nit、好み、過剰な rewrite は rejected にする。
   - accepted finding は、どの品質軸を壊しているか明示する。

7. closeout する。
   - 課題一覧、優先度、推奨修正順を示す。
   - 修正を行った場合は `review-diff-skill` で差分レビューする。
   - 永続化操作や配布操作は、この skill の対象外として扱う。

## Output

```md
## Evaluation
- Static contract check: 実施結果の要約
- Smoke check: 実施 case、pass/fail、fresh agent / subagent を使ったか
- Runtime smoke check: 実施した / 不要 / 実施不能と理由
- Accepted findings: 件数と要約
- Rejected findings: 件数と理由

## Smoke check

| Case | Input | Expected | Actual | Result | Evidence | Finding link |
| --- | --- | --- | --- | --- | --- | --- |
| <case> | <input> | <expected> | <actual> | pass/fail | <evidence> | <finding or —> |

## Findings

### [severity] title
- Target: path:line
- Axis: metadata / description / predictability / hierarchy / deterministic resources / completion / pruning / failure modes / safety
- Problem: agent がどう誤作動するか、または何が保守しづらくなるか
- Evidence: skill 本文、description、smoke check からの根拠
- Suggested fix: 最小修正
- Judgment link: この修正が満たす smoke case の Expected / Result
```

finding がない場合は、`reviewing-skills` protocol と smoke check を実施したうえで actionable finding がないことを明示する。
