---
name: audit-skills
description: skill inventory を定期棚卸しし、skill 群を横断した routing conflict、責務重複、single source of truth 破れ、粒度問題、sprawl / sediment を検出して次アクションを整理する。単一 skill の詳細レビュー、skill 作成前の軽い近接確認、実際の編集・統合・削除・配布操作では使わない。
disable-model-invocation: true
---

skill 群を横断して棚卸しし、重複・責務衝突・肥大化の候補を cluster 単位で報告する。
この skill は audit report を作るだけで、skill 本文の編集、統合、削除、commit、push、APM pin 更新、install は行わない。

## Scope

- 主用途は定期棚卸し。
- 標準対象は現在の source-of-truth repo にある skill 群。
- 必要時だけ global 展開先（例: `~/.agents/skills`、`~/.claude/skills`）との差分や drift を補助的に確認する。
- 新規 skill 作成前の軽い近接確認は `create-skill` の責務として扱う。
- 単一 skill の深いレビューは `review-skill` に委譲する。
- skill 変更 diff の配布前 gate は `review-diff-skill` に委譲する。

## Audit Axes

優先度は routing conflict を最上位に置く。

1. routing conflict
   - 同じ依頼で複数 skill が起動候補になる。
   - 本来起動すべき skill が description / name / README 導線から見つかりにくい。
   - positive trigger と negative trigger が近接 skill と衝突している。
2. responsibility overlap
   - 複数 skill が実質的に同じ作業、同じ成果物、同じ判断を担当している。
   - wrapper と reusable discipline の境界が曖昧になっている。
3. single source of truth break
   - 同じ rule、rubric、workflow、配布 gate が複数 skill に authoritative に存在する。
   - 片方を変えるともう片方も変えないと drift する構造になっている。
4. granularity problem
   - model-invoked skill と user-invoked skill の粒度が不適切。
   - 独立 invocation に値しない skill が増えて context load / cognitive load を増やしている。
   - 本来分けるべき sequence や branch が 1 skill に詰め込まれている。
5. sprawl / sediment
   - `SKILL.md` が長く、通常 path に不要な reference が混ざっている。
   - 古い前提、廃止済み名称、今は使わない branch が残っている。
   - README や関連 docs と skill 本文が二重管理になっている。

## Severity

- high: routing conflict により、同じ依頼で複数 skill が起動候補になる、または本来の skill が見つからない可能性が高い。
- medium: responsibility overlap、single source of truth break、granularity problem により、保守時の drift や使い分けの迷いが起きる可能性が高い。
- low: sprawl / sediment や軽い導線不整合があるが、誤発火・不発火や二重管理の直接原因とはまだ言えない。

## Workflow

1. 対象 repository と補助確認の有無を決める。
   - ユーザーが対象 path を指定した場合は、その path を source-of-truth として扱う。
   - path 指定がなく、現在の working directory が skill repo なら、現在の repo を source-of-truth として扱う。
   - global 展開先との drift 確認は、ユーザーが明示した場合か、source-of-truth と実利用状態の不一致が疑われる場合だけ行う。
   - global drift を確認しない場合は、report に global drift 未確認と書く。

2. Inventory pass を行う。
   - `find` / `rg` で `SKILL.md` を列挙する。
   - 各 skill の frontmatter から `name`、`description`、`disable-model-invocation` を読む。
   - 配置 category、README / category README の導線、skill 名と directory 名の一致を確認する。
   - 本文全文はこの段階では読まない。frontmatter と導線だけで cluster 候補を作る。

3. Cluster 候補を作る。
   - 近い leading word、同じ成果物、同じ lifecycle、同じ gate、同じ category、README 上の近接導線を手がかりにまとめる。
   - routing conflict の疑いがある cluster を優先する。
   - cluster に入れなかった skill も inventory summary には数える。

4. Cluster deep-dive を subagent に並列依頼する。
   - cluster ごとに独立した subagent を使う。
   - subagent には対象 skill path、5 つの audit axes、編集禁止、根拠必須を渡す。
   - subagent には inventory 全体の severity 最終判断を委譲しない。
   - cluster が少ない、または subagent を使えない環境では main agent が deep-dive し、理由を report に書く。

5. Subagent findings を検証する。
   - subagent の finding をそのまま採用しない。
   - 対象 `SKILL.md`、関連 `references/`、README を main agent が直接読み、根拠が確認できるものだけ accepted にする。
   - APM 設定は、ユーザーが path を指定した場合、または repo 内に明示的な APM 設定がある場合だけ読む。見つからない場合は未確認と report に書く。
   - speculative risk、文言類似だけ、共有 rubric の正当な参照、意図された wrapper / discipline 分離は rejected にする。

6. Severity と次アクションを決める。
   - routing conflict は最優先で扱う。
   - 次に responsibility overlap、single source of truth break、granularity problem、sprawl / sediment の順で見る。
   - 次アクションは、`review-skill` 実行、description の narrow、merge proposal、split proposal、single source of truth 抽出、no action のように整理する。
   - この skill 内では実際の編集に進まない。

7. Audit report を出す。
   - cluster 単位で、問題、根拠、推奨次アクションを示す。
   - rejected candidates も短く残し、次回 audit で同じ候補を再発見しにくくする。
   - commit、push、APM pin 更新、install を実行していないことを明示する。

## Subagent Contract

cluster deep-dive worker には次の形式で依頼する。

```md
You are a cluster deep-dive worker for `audit-skills`.
Do not edit files. Do not propose commits, pushes, APM pin updates, or installs.

## Cluster
- Name: <cluster name>
- Candidate reason: <routing / responsibility / shared rule / category / README adjacency>
- Skill paths:
  - <path/to/SKILL.md>

## Audit axes
1. routing conflict
2. responsibility overlap
3. single source of truth break
4. granularity problem
5. sprawl / sediment

## Task
1. Read the listed SKILL.md files and directly related references only when needed.
2. Identify high-confidence finding candidates within this cluster.
3. For each candidate, provide exact path:line evidence or a short excerpt.
4. Mark speculative or wording-only similarities as rejected candidates.
5. Do not decide global severity beyond this cluster.

## Report
### Finding candidates
- Title:
- Axis:
- Problem:
- Evidence:
- Suggested next action:

### Rejected candidates
- Candidate:
- Reason rejected:

### Notes
- Files read:
- Unclear points:
```

## Output

```md
## Inventory Summary
- Source of truth: <path>
- Skills scanned: <n>
- Model-invoked: <n>
- User-invoked: <n>
- Global drift checked: yes/no
- Subagents used: <n or reason not used>

## Clusters

### <cluster name>
- Skills: <paths>
- Why clustered: routing / responsibility / shared reference / category / README adjacency

## Findings

### [severity] <title>
- Cluster: <cluster>
- Axis: routing conflict / responsibility overlap / single source of truth / granularity / sprawl-sediment
- Problem: <agent がどう誤作動するか、または何が保守しづらくなるか>
- Evidence: <path:line + excerpt>
- Suggested next action: review-skill / description narrow / merge proposal / split proposal / single source extraction / no action
- Do not do now: actual edit / delete / commit / push / pin / install

## Rejected candidates
- Candidate: <summary>
- Reason rejected: speculative / shared rubric acceptable / wording similarity only / intentional wrapper-discipline split / insufficient evidence

## Recommended order
1. <next action>
2. <next action>

## Safety
- Edited files: no
- Deleted files: no
- commit / push / APM pin update / install: not run
```

finding がない場合も、inventory summary、cluster の作り方、rejected candidates、safety を報告し、actionable finding がないことを明示する。

## Done Criteria

- source-of-truth repo の skill inventory を数えた。
- cluster 候補を作り、routing conflict を最優先で確認した。
- deep-dive した cluster では、5 つの audit axes を適用した。
- accepted finding と rejected candidate を分けた。
- 次アクションを示したが、実際の編集・削除・commit・push・APM pin 更新・install は行っていない。
