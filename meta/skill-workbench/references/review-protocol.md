# Skill Review Protocol

この reference は Review diff / Review whole branch で読む。
レビューは変更または対象 skill が持つ contract を特定し、その risk に必要な check だけを選ぶ。
静的読解だけでは実行時のズレを判断できない場合は、fresh agent / subagent の smoke check を使う。

## Contract Map

最初に対象から次の contract を地図化する。

- outcome: skill が作るユーザー可視の到達状態。
- routing: positive / negative trigger、branch selection。
- authority / safety: 自律実行と確認が必要な action の境界。
- evidence: 判断と action の前提。
- completion / output: 終了状態と報告内容。
- context interface: `SKILL.md`、references、assets、scripts、外部 reference の読み分け。

Review diff では変更された contract と preservation set の交差だけを詳しく見る。
Review whole では contract map 全体を見る。

## Review Rubric

対象に関係する軸だけを選び、選択理由を報告する。

| Axis | 見る contract |
| --- | --- |
| metadata / routing | name、directory、description、positive / negative trigger、branch 対応 |
| outcome / completion | outcome、branch-level completion、必須 output、残 finding の扱い |
| authority / safety | permission gate、destructive / external / costly action、scope expansion |
| evidence / failure | prerequisite、判断根拠、情報不足時の fallback |
| context interface | progressive disclosure、single source of truth、rich reference、tool / script interface |
| constraint quality | domain 固有の invariant と不要な探索手順の区別、矛盾、overconstraint |
| deterministic resources | schema / asset / script / test に移すべき反復処理 |
| pruning | no-op、重複、古い前提、周辺 context から明白な説明 |

すべての軸を機械的に埋めない。
ただし routing、authority / safety、branch-level completion は変更されていないことを preservation set で確認する。

## Static Contract Check

すべての review で必須。

- dirty worktree では tracked diff と untracked の skill resources を確認する。
- contract map と変更内容から relevant axes を選ぶ。
- routing、branch-level completion、authority / safety の preservation を確認する。
- rule の列挙より既存 code、test、schema、tool interface のほうが高い忠実度で表せないか確認する。
- scope gap や矛盾があれば、smoke check より先に修正候補とする。

## Smoke Check

fresh agent / subagent に自然な入力と必要最小限の状況を渡し、どの `SKILL.md` を読んでどう実行したかを観測する。
作者や同じ reviewer の mental walkthrough で代替しない。

### Selection

| Change / risk | Smoke |
| --- | --- |
| routing、description、branch selection | Discovery。harness-real に実行できる場合 |
| authority / safety、主要 workflow、branch completion | Execution |
| reference 構造、output contract、判断 rubric | Static で不十分なら Execution |
| 外部 CLI、生成、Git、install、build、API に依存 | Runtime |
| typo、formatting、リンク、一覧だけ | 不要。Skip |

新規 skill と大幅変更では Execution smoke を行う。
それ以外は Static Contract Check で未解決の risk がある場合に行う。

### Execution Smoke

対象 skill が選択済みであることを前提に、自然な依頼と repo / task 状況で本文どおり実行できるかを見る。

- expected は skill 名や内部手順ではなく、外部観測可能な outcome、gate、evidence で書く。
- subagent を使えない場合は、理由と観測限界を報告し、実行済みとは言わない。

### Discovery Smoke

model-invoked skill の description / trigger を評価するときに実施する。
対象 skill 名や path を渡さず、harness が実際に discovery する環境で fresh subagent を起動し、対象 `SKILL.md` が読まれるかを見る。

- positive case 1 件以上、negative near-miss 1 件以上を用意する。
- Execution smoke が pass しても Discovery smoke の代替にはしない。
- harness-real な Discovery smoke を用意できない場合は未検証として報告する。

### Runtime Smoke

skill の期待動作が外部 CLI、ファイル生成、Git 操作、sandbox / temp repo、install、build、test、lint、API call に依存する場合に実行する。

- 一時 repo / sandbox を使い、global / user environment を明示許可なしに変更しない。
- 実行した command、diff、生成ファイル、触った scope、結果を報告する。
- 必要だが実行できない場合は、理由と残リスクを明示する。

## Check Interface

```md
## Evaluation
- Scope: <diff / whole と対象>
- Contract map: <変更・評価した contract>
- Relevant axes: <選んだ軸と理由>
- Static contract check: <結果>
- Smoke checks: <実施 / 不要 / 実施不能と理由>
- Accepted findings: <件数と要約>
- Rejected findings: <件数と理由>
- Residual risk: <未検証事項>

## Smoke checks
| Case | Input | Expected | Actual | Result | Evidence | Finding |
| --- | --- | --- | --- | --- | --- | --- |

## Findings
### [severity] title
- Target: <path:line>
- Contract: <contract map の項目>
- Problem: <想定される誤作動または保守上の破れ>
- Evidence: <本文、diff、または smoke の根拠>
- Suggested fix: <最小修正>
- Verification: <修正後に確認する evidence>
```

Skip の場合は、対象 diff、実行契約に影響しない理由、residual risk だけを報告する。

## Interpretation Rules

- smoke failure は Expected と Actual の差分として扱う。
- subagent の「skill を使った」という自己申告だけを根拠にしない。
- verbose log、read files、tool calls、commands、generated diff、final output を確認できる範囲で evidence にする。
- harness や tool 制約による failure を skill 本文の finding と混同しない。
- 2 回以上同じ pattern で失敗する場合は、文言パッチではなく構造分割や workflow 再設計を検討する。
- checklist completion ではなく、outcome、gate、evidence が満たされたかで判定する。

## Finding Rules

- high-confidence かつ action 可能な finding だけ accepted にする。
- target、contract、problem、evidence、suggested fix、verification を持たせる。
- smoke case の critical expected を落とす問題は high severity として扱う。
- speculative risk、cosmetic nit、好み、過剰な rewrite は rejected にする。
