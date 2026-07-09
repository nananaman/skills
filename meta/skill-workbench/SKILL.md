---
name: skill-workbench
description: agent skill の作成・改善・レビュー・棚卸しを予測可能な process にする workbench。
disable-model-invocation: true
---

agent skill の lifecycle workbench。
目的は、確率的に振る舞う agent から予測可能なプロセスを引き出す小さな skill 群を、作成・改善・レビュー・棚卸しまで一貫して扱うこと。

## Branch Router

最初に対象 branch を 1 つ選ぶ。
複数 branch にまたがる場合も、完了条件が混ざらないように上から順に処理する。

| Branch | 使う場面 | 完了条件 |
| --- | --- | --- |
| Create / Improve | 新規 skill 作成、既存 skill の draft 改善、description / routing 改善 | draft または変更差分ができ、該当 review branch を通して actionable finding が残っていない |
| Review diff | skill 変更 diff の配布前確認、README / APM manifest / references を含む skill 関連 diff の regression 確認 | skip decision、または static contract check / smoke check / runtime smoke 判定を含む review result を返した |
| Review whole | 新規 skill、大幅変更、高頻度 skill、過去に誤作動した skill、責務過多が疑われる skill の全体レビュー | 対象 skill の目的・routing・本文・関連ファイルを見て、actionable finding と rejected finding を分けた |
| Audit inventory | skill inventory の定期棚卸し、routing conflict、責務重複、single source of truth 破れ、粒度問題、sprawl / sediment の横断検出 | inventory summary、cluster、accepted / rejected finding、推奨順、安全確認を報告した |

## Common Rules

- skill の目的は、毎回同じ出力ではなく、毎回同じ種類の手順・判断・探索を行わせること。
- `SKILL.md` は branch router と通常 path の手順に絞る。詳細な原則、review protocol、audit protocol、eval loop は `references/` を必要時だけ読む。
- description は、skill 読み込み前に agent が見る routing 情報として扱う。紹介文や本文要約にしない。
- 各 step は agent が判定できる completion criterion で終える。
- finding は high-confidence かつ action 可能なものだけ accepted にする。
- speculative risk、cosmetic nit、好み、過剰な rewrite は rejected にする。
- commit、push、APM pin 更新、install は、ユーザーの明示依頼がない限り実行しない。

## Create / Improve

1. 目的を固定する。
   - 何をできるようにする skill か。
   - いつ起動すべきか。
   - 起動すべきでない近接領域は何か。
   - 期待出力と完了条件は何か。
   - project 固有か、汎用 skill か。

2. 近接確認を行う。
   - 新規 skill の場合、同じ成果物、同じ leading word、同じ lifecycle、同じ gate を持つ既存 skill がないか確認する。
   - 近接 skill がある場合、merge / split / description narrow / no action のどれかを決める。
   - 横断棚卸しが必要な規模なら、この branch を止めて Audit inventory branch を先に実行する。

3. `references/design-principles.md` を読む。
   - invocation、branches、information hierarchy、completion criteria、failure modes、leading words を決める。
   - completion: 本文に入れる情報、reference に逃がす情報、別 skill にすべき情報を分けた。

4. 起動方式と配置を決める。
   - model-invoked: agent が自律発火すべき、または他 skill から到達させる必要がある。
   - user-invoked: 人間が明示起動するだけでよい。`disable-model-invocation: true` を付ける。
   - 汎用 skill は `nananaman/skills` の適切な category に置く。project 固有 skill は対象 project の local skill directory に置く。

5. draft または変更を作る。
   - `name:` は directory 名と一致させる。小文字、数字、単一ハイフンのみ、1〜64 文字。
   - description は positive trigger と negative trigger を含む routing 情報にする。
   - `SKILL.md` は agent の判断・手順・停止条件・出力形式を変える情報だけを書く。
   - 長い説明、用語、例、評価手順は `references/` へ逃がす。
   - テンプレート、schema、静的素材は `assets/` に置く。
   - 壊れやすい解析や繰り返し boilerplate は tiny CLI として `scripts/` に置くことを検討する。

6. 必要なら eval loop を使う。
   - routing が難しい、品質問題が再発している、客観評価できる成果物を生成する skill では `references/eval-loop.md` を読む。
   - completion: baseline / with-skill の比較、または実行不能理由を報告できる。

7. review branch を実行する。
   - 新規 skill、大幅変更、高頻度 skill、過去に誤作動した skillは Review whole branch。
   - 既存 skill の差分改善、README / APM manifest / references を含む変更は Review diff branch。
   - actionable finding があれば修正し、該当 review branch を再実行する。

## Review diff

1. レビュー対象 diff を決める。
   - dirty worktree があれば local diff を対象にする。
   - dirty worktree では tracked diff だけでなく untracked files も対象にする。`??` の `SKILL.md`、`references/`、`GLOSSARY.md`、`assets/`、`scripts/`、関連 README、APM manifest は file read で内容を確認し、`git diff` が空でも変更なしと判断しない。
   - commit 済みなら commit diff、branch 作業なら branch diff を対象にする。
   - skill 以外の変更が混ざっていれば、skill 変更とそれ以外を分けて扱う。

2. Applicability check を行う。
   - 変更された `SKILL.md`、`references/`、`GLOSSARY.md`、`assets/`、`scripts/`、関連 README を確認する。
   - diff が routing、判断条件、workflow、停止条件、出力形式、reference / asset / script の使われ方、safety / failure handling のいずれかを変えるか判定する。
   - 実行契約に影響しない typo、formatting、リンク整理、一覧更新だけなら Skip decision を返して止める。
   - 迷う場合は対象として扱う。

3. `references/review-protocol.md` を読み、Static contract check と Smoke check を設計する。
   - skill 変更が実行契約に影響する場合、fresh agent / subagent による Execution smoke を省略しない。
   - model-invoked skill の description / trigger 変更では Discovery smoke も試みる。
   - runtime behavior に依存する skill では Runtime smoke check も判定する。

4. diff 固有の regression を見る。
   - trigger が広がりすぎていないか、狭まりすぎていないか。
   - negative trigger の削除や曖昧化で近接領域に過発火しないか。
   - 新しい手順が既存の停止条件を迂回していないか。
   - 削除された文が safety gate、user confirmation、failure handling を担っていなかったか。
   - 通常 path に不要な context を積んでいないか。

5. 必要なら Review whole へ escalate する。
   - 新規 skill。
   - model-invoked skill の description を変えた。
   - 高頻度利用 skill。
   - 過去に誤作動した skill。
   - skill の責務や workflow を大きく変えた。

6. Output に従って報告する。

### Skip decision output

```md
## Skip decision
- Reason: skill の routing / 判断 / 手順 / 停止条件 / 出力形式 / safety に影響しないため
- Checked diff: <対象ファイルと変更要約>
- Residual risk: <あれば短く。なければ none>
```

### Review diff output

```md
## Evaluation
- Applicability: 対象にした理由
- Static contract check: 実施結果の要約
- Smoke check: 実施 case、pass/fail、fresh agent / subagent を使ったか
- Runtime smoke check: 実施した / 不要 / 実施不能と理由
- Escalated to Review whole: yes / no と理由
- Accepted findings: 件数と要約
- Rejected findings: 件数と理由

## Smoke check
| Case | Input | Expected | Actual | Result | Evidence | Finding link |
| --- | --- | --- | --- | --- | --- | --- |

## Findings
### [severity] title
- Target: path:line
- Axis: metadata / description / predictability / hierarchy / deterministic resources / completion / pruning / failure modes / safety
- Problem: agent がどう誤作動するか、または何が保守しづらくなるか
- Evidence: diff、対象本文、関連ファイル、smoke 結果からの根拠
- Suggested fix: 最小修正
- Judgment link: この修正が満たす smoke case の Expected / Result
```

## Review whole

1. 対象 skill と目的を確認する。
   - 対象の `SKILL.md`、`references/`、`GLOSSARY.md`、`assets/`、`scripts/`、`NOTICE.md`、README 記載を読む。
   - その skill が解く作業、起動すべき場面、起動すべきでない場面を列挙する。
   - `name:` と配置 directory、description の positive / negative trigger を確認する。

2. `references/review-protocol.md` を読み、Static contract check、Smoke check、必要なら Runtime smoke check を実行する。
   - Execution smoke は原則必須。
   - model-invoked skill では Discovery smoke も試みる。
   - harness-real な Discovery smoke を実行できない場合は、未検証の残リスクとして報告し、Execution smoke で代替したと言わない。

3. 全体構造を評価する。
   - 1 skill に複数の責務が詰め込まれていないか。
   - model-invoked にすべき共通概念と user-invoked wrapper が混ざっていないか。
   - 作成 workflow、diff review、全体 review、audit、配布 workflow が completion criteria なしに混ざっていないか。
   - `SKILL.md` が通常 path の手順へ絞られているか。
   - references / assets / scripts が必要時だけ読まれる構造か。

4. findings を整理する。
   - smoke check の failure と対象本文を対応づける。
   - 対象本文と根拠が確認できるものだけ accepted にする。
   - 修正を行った場合は Review diff branch で差分レビューする。

5. Output に従って報告する。

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

## Findings
### [severity] title
- Target: path:line
- Axis: metadata / description / predictability / hierarchy / deterministic resources / completion / pruning / failure modes / safety
- Problem: agent がどう誤作動するか、または何が保守しづらくなるか
- Evidence: skill 本文、description、関連ファイル、smoke check からの根拠
- Suggested fix: 最小修正
- Judgment link: この修正が満たす smoke case の Expected / Result
```

## Audit inventory

1. `references/audit-protocol.md` を読む。
2. source-of-truth repo と補助確認の有無を決める。
3. inventory pass で skill の frontmatter、配置 category、README 導線、directory / `name:` 一致を確認する。
4. routing conflict を優先して cluster 候補を作る。
5. cluster deep-dive を行い、subagent を使える場合は cluster ごとに並列化する。
6. subagent finding は main agent が対象本文と関連ファイルで検証する。
7. accepted finding、rejected candidate、推奨順、安全確認を報告する。

## Safety

- この workbench は作成・編集・レビュー・棚卸しを扱うが、commit / push / pin / install は自動実行しない。
- destructive deletion、rename、統合はユーザーが明示した場合だけ実行する。
- 永続ファイルへ失敗パターン台帳を書く場合は、ユーザーに確認する。確認がない場合は session 内で管理する。
