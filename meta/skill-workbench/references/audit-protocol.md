# Skill Inventory Audit Protocol

この reference は Audit inventory branch で読む。
目的は、skill 群を横断して routing conflict、責務重複、single source of truth 破れ、粒度問題、sprawl / sediment を cluster 単位で検出すること。

## Scope

- 標準対象は現在の source-of-truth repo にある skill 群。
- 必要時だけ global 展開先との差分や drift を補助確認する。
- audit は report を作るだけで、編集、削除、commit、push、APM pin 更新、install は行わない。
- 単一 skill の深い修正は Create / Improve または Review whole branch に渡す。

## Audit Axes

1. routing conflict
   - 同じ依頼で複数 skill が起動候補になる。
   - 本来起動すべき skill が description / name / README 導線から見つかりにくい。
   - positive trigger と negative trigger が近接 skill と衝突している。

2. responsibility overlap
   - 複数 skill が同じ作業、成果物、判断を担当している。
   - wrapper と reusable discipline の境界が曖昧。

3. single source of truth break
   - 同じ rule、rubric、workflow、配布 gate が複数 skill に authoritative に存在する。
   - 片方を変えるともう片方も変える必要がある。

4. granularity problem
   - model-invoked skill と user-invoked skill の粒度が不適切。
   - 独立 invocation に値しない skill が context load / cognitive load を増やしている。
   - 本来分けるべき sequence や branch が 1 skill に詰め込まれている。

5. sprawl / sediment
   - `SKILL.md` が長く、通常 path に不要な reference が混ざっている。
   - 古い前提、廃止済み名称、今は使わない branch が残っている。
   - README や関連 docs と skill 本文が二重管理になっている。

## Severity

- high: routing conflict により誤発火・不発火の可能性が高い。
- medium: responsibility overlap、single source of truth break、granularity problem により drift や使い分け迷いが起きる可能性が高い。
- low: sprawl / sediment や軽い導線不整合があるが、誤発火・不発火や二重管理の直接原因とはまだ言えない。

## Workflow

1. 対象 repository と補助確認の有無を決める。
   - path 指定がなく、現在の working directory が skill repo なら現在の repo を source-of-truth とする。
   - global drift を確認しない場合は report に未確認と書く。

2. Inventory pass を行う。
   - `SKILL.md` を列挙する。
   - 各 skill の frontmatter から `name`、`description`、`disable-model-invocation` を読む。
   - 配置 category、README / category README 導線、skill 名と directory 名の一致を確認する。
   - 本文全文はこの段階では読まない。

3. Cluster 候補を作る。
   - 近い leading word、同じ成果物、同じ lifecycle、同じ gate、同じ category、README 上の近接導線を手がかりにする。
   - routing conflict の疑いがある cluster を優先する。

4. Cluster deep-dive を行う。
   - cluster ごとに独立した subagent を使える場合は並列化する。
   - subagent には対象 skill path、5 つの audit axes、編集禁止、根拠必須を渡す。
   - subagent には inventory 全体の severity 最終判断を委譲しない。

5. Subagent finding を検証する。
   - finding をそのまま採用しない。
   - 対象 `SKILL.md`、関連 `references/`、README を main agent が直接読み、根拠が確認できるものだけ accepted にする。
   - speculative risk、文言類似だけ、共有 rubric の正当な参照、意図された wrapper / discipline 分離は rejected にする。

6. Severity と次アクションを決める。
   - routing conflict を最優先。
   - 次に responsibility overlap、single source of truth break、granularity problem、sprawl / sediment。
   - 次アクションは Review whole、description narrow、merge proposal、split proposal、single source extraction、no action のように整理する。

## Subagent Contract

```md
You are a cluster deep-dive worker for skill-workbench Audit inventory.
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
- Suggested next action: Review whole / description narrow / merge proposal / split proposal / single source extraction / no action
- Do not do now: actual edit / delete / commit / push / pin / install

## Rejected candidates
- Candidate: <summary>
- Reason rejected: speculative / shared rubric acceptable / wording similarity only / intentional wrapper-discipline split / insufficient evidence

## Recommended order
1. <next action>

## Safety
- Edited files: no
- Deleted files: no
- commit / push / APM pin update / install: not run
```
